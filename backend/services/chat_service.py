from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Protocol

from openai import AsyncOpenAI

from config import Settings
from crew import (
    CrewRuntimeConfig,
    crew_graph_to_dict,
    run_dynamic_research_crew_with_trace,
)
from knowledge_base import CompanyKnowledgeBase
from services.drive_context import build_google_drive_context


class ChatMessageLike(Protocol):
    role: str
    content: str


class TranslateRequestLike(Protocol):
    text: str
    target_language: str
    preserve_markdown: bool


def serialize_messages(messages: list[ChatMessageLike]) -> list[dict[str, str]]:
    return [{"role": msg.role, "content": msg.content} for msg in messages]


def inject_company_context(
    messages: list[ChatMessageLike],
    company_context: str,
) -> list[dict[str, str]]:
    serialized = serialize_messages(messages)
    if not company_context:
        return serialized

    rag_system_prompt = (
        "You are a company-specialized assistant. "
        "Prioritize the provided company knowledge when answering. "
        "If the answer is not in the provided company materials, say so clearly.\n\n"
        "[Company Knowledge]\n"
        f"{company_context}"
    )

    return [{"role": "system", "content": rag_system_prompt}, *serialized]


def latest_user_prompt(messages: list[ChatMessageLike]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return messages[-1].content


async def run_default_llm_chat(
    client: AsyncOpenAI,
    settings: Settings,
    messages: list[ChatMessageLike],
    company_context: str,
) -> str:
    completion = await client.chat.completions.create(
        model=settings.llm_model,
        messages=inject_company_context(messages, company_context),
    )
    return completion.choices[0].message.content or ""


async def run_translation(
    client: AsyncOpenAI,
    settings: Settings,
    req: TranslateRequestLike,
) -> str:
    requested_language = req.target_language.strip() or "ko"
    normalized_language = requested_language.lower()
    target_language = (
        "Korean"
        if normalized_language in {"ko", "ko-kr", "kr", "korean", "한국어"}
        else requested_language
    )

    preserve_style = (
        "Preserve markdown structure, tables, headings, lists, links, and code blocks exactly."
        if req.preserve_markdown
        else "You may freely format the translation for readability."
    )

    completion = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a professional translator. "
                    f"Translate the user text into {target_language}. "
                    "Return only the translated content without commentary. "
                    f"{preserve_style}"
                ),
            },
            {"role": "user", "content": req.text},
        ],
    )
    return (completion.choices[0].message.content or "").strip()


async def run_crewai_report(
    user_prompt: str,
    settings: Settings,
    company_context: str,
    on_progress: Callable[[dict[str, object]], None] | None = None,
) -> tuple[str, dict[str, object]]:
    prompt_for_execution = user_prompt
    if company_context:
        prompt_for_execution = (
            f"{user_prompt}\n\n"
            "Use the following company knowledge as grounded context.\n"
            f"{company_context}"
        )

    runtime = CrewRuntimeConfig(
        llm_model=settings.llm_model,
        llm_base_url=settings.llm_base_url,
        llm_api_key=settings.llm_api_key,
        crewai_model=settings.crewai_model,
        web_search_results=settings.crewai_web_search_results,
    )
    execution = await asyncio.to_thread(
        run_dynamic_research_crew_with_trace,
        prompt_for_execution,
        runtime,
        on_progress,
    )
    return execution.report, crew_graph_to_dict(execution.graph)


async def load_company_context(
    user_prompt: str,
    settings: Settings,
    *,
    knowledge_base: CompanyKnowledgeBase,
    client: AsyncOpenAI,
    google_api_key: str,
) -> tuple[str, list[dict[str, object]]]:
    context_sections: list[str] = []
    sources: list[dict[str, object]] = []

    if settings.rag_enabled and knowledge_base.chunk_count > 0:
        rag_context, rag_sources = await knowledge_base.build_context(
            query=user_prompt,
            client=client,
            embedding_model=settings.rag_embedding_model,
            top_k=settings.rag_top_k,
        )
        if rag_context:
            context_sections.append(f"[Uploaded Company Knowledge]\n{rag_context}")
            sources.extend(rag_sources)

    drive_context, drive_sources, drive_error = await build_google_drive_context(
        query=user_prompt,
        settings=settings,
        google_api_key=google_api_key,
    )
    if drive_context:
        context_sections.append(f"[Google Drive Shared Files]\n{drive_context}")
        sources.extend(drive_sources)
    elif drive_error:
        print(f"⚠️ Google Drive context skipped: {drive_error}")

    if not context_sections:
        return "", []

    return "\n\n".join(context_sections), sources
