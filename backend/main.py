from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import asyncio
import json
from typing import Literal

from fastapi import FastAPI, Depends, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel, Field, field_validator

from config import Settings, get_settings
from crew_orchestrator import (
    CrewRuntimeConfig,
    crew_graph_to_dict,
    run_dynamic_research_crew_with_trace,
    should_route_to_crewai,
)
from knowledge_base import CompanyKnowledgeBase, extract_text_from_upload


# ─── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.llm_client = AsyncOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
    )
    app.state.knowledge_base = CompanyKnowledgeBase(settings.rag_storage_path)
    print(f"✅ LLM client ready  model={settings.llm_model}  url={settings.llm_base_url}")
    print(f"✅ Knowledge base ready path={settings.rag_storage_path}")
    yield
    await app.state.llm_client.close()


# ─── App ──────────────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(title="Orchestration", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app


app = create_app()


# ─── Schemas ──────────────────────────────────────────────────────────────────
class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1, max_length=16_000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("content contains invalid null characters")
        if not value.strip():
            raise ValueError("content must not be empty")
        return value.replace("\r\n", "\n")


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=200)
    session_id: str = Field(default="default", min_length=1, max_length=120)
    stream: bool = False

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("session_id must not be empty")
        if any(ord(ch) < 32 for ch in normalized):
            raise ValueError("session_id contains control characters")
        return normalized


class ChatResponse(BaseModel):
    message: str
    session_id: str
    source: str | None = None
    crew_graph: dict[str, object] | None = None
    knowledge_sources: list[dict[str, object]] | None = None


class KnowledgeUploadResponse(BaseModel):
    filename: str
    chunk_count: int
    total_chunks: int
    embedded: bool
    documents: list[str]
    updated_at: str | None = None


class KnowledgeStatusResponse(BaseModel):
    rag_enabled: bool
    chunk_count: int
    documents: list[str]
    updated_at: str | None = None


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=32_000)
    target_language: str = Field(default="ko", min_length=2, max_length=40)
    preserve_markdown: bool = True

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("text contains invalid null characters")
        normalized = value.replace("\r\n", "\n").strip()
        if not normalized:
            raise ValueError("text must not be empty")
        return normalized


class TranslateResponse(BaseModel):
    translated_text: str
    target_language: str
    source: str = "llm"


def serialize_messages(messages: list[ChatMessage]) -> list[dict[str, str]]:
    return [{"role": m.role, "content": m.content} for m in messages]


def inject_company_context(
    messages: list[ChatMessage],
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


def latest_user_prompt(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return messages[-1].content


async def run_default_llm_chat(
    client: AsyncOpenAI,
    settings: Settings,
    messages: list[ChatMessage],
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
    req: TranslateRequest,
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
    )
    return execution.report, crew_graph_to_dict(execution.graph)


async def load_company_context(
    user_prompt: str,
    settings: Settings,
) -> tuple[str, list[dict[str, object]]]:
    if not settings.rag_enabled:
        return "", []

    knowledge_base: CompanyKnowledgeBase = app.state.knowledge_base
    if knowledge_base.chunk_count == 0:
        return "", []

    return await knowledge_base.build_context(
        query=user_prompt,
        client=app.state.llm_client,
        embedding_model=settings.rag_embedding_model,
        top_k=settings.rag_top_k,
    )


# ─── Routes ───────────────────────────────────────────────────────────────────
@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/translate", response_model=TranslateResponse)
async def translate(
    req: TranslateRequest,
    settings: Settings = Depends(get_settings),
) -> TranslateResponse:
    client: AsyncOpenAI = app.state.llm_client
    try:
        translated = await run_translation(client, settings, req)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Translation failed: {exc}") from exc

    if not translated:
        raise HTTPException(status_code=502, detail="Translation failed: empty response")

    return TranslateResponse(
        translated_text=translated,
        target_language=req.target_language,
        source="llm",
    )


@app.get("/knowledge/status", response_model=KnowledgeStatusResponse)
async def knowledge_status(
    settings: Settings = Depends(get_settings),
) -> KnowledgeStatusResponse:
    knowledge_base: CompanyKnowledgeBase = app.state.knowledge_base
    status = knowledge_base.status()
    return KnowledgeStatusResponse(
        rag_enabled=settings.rag_enabled,
        chunk_count=int(status["chunk_count"]),
        documents=list(status["documents"]),
        updated_at=(
            str(status["updated_at"])
            if status["updated_at"] is not None
            else None
        ),
    )


@app.post("/knowledge/upload", response_model=KnowledgeUploadResponse)
async def knowledge_upload(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
) -> KnowledgeUploadResponse:
    if not settings.rag_enabled:
        raise HTTPException(status_code=400, detail="RAG is disabled")

    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    max_upload_bytes = settings.rag_max_upload_mb * 1024 * 1024
    if len(content) > max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {settings.rag_max_upload_mb} MB)",
        )

    try:
        extracted_text = extract_text_from_upload(filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not extracted_text.strip():
        raise HTTPException(status_code=400, detail="No readable text found in file")

    knowledge_base: CompanyKnowledgeBase = app.state.knowledge_base
    result = await knowledge_base.ingest_document(
        document_name=filename,
        text=extracted_text,
        client=app.state.llm_client,
        embedding_model=settings.rag_embedding_model,
        max_chunk_chars=settings.rag_max_chunk_chars,
        chunk_overlap=settings.rag_chunk_overlap,
    )

    return KnowledgeUploadResponse(
        filename=filename,
        chunk_count=int(result["chunk_count"]),
        total_chunks=int(result["total_chunks"]),
        embedded=bool(result["embedded"]),
        documents=list(result["documents"]),
        updated_at=(
            str(result["updated_at"])
            if result["updated_at"] is not None
            else None
        ),
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    client: AsyncOpenAI = app.state.llm_client
    user_prompt = latest_user_prompt(req.messages)
    company_context, knowledge_sources = await load_company_context(user_prompt, settings)

    if settings.crewai_enabled and should_route_to_crewai(user_prompt):
        try:
            reply, crew_graph = await run_crewai_report(
                user_prompt,
                settings,
                company_context,
            )
            return ChatResponse(
                message=reply,
                session_id=req.session_id,
                source="crewai",
                crew_graph=crew_graph,
                knowledge_sources=knowledge_sources or None,
            )
        except Exception as exc:
            print(f"⚠️ CrewAI failed in /chat, using default LLM fallback: {exc}")

    reply = await run_default_llm_chat(
        client,
        settings,
        req.messages,
        company_context,
    )
    return ChatResponse(
        message=reply,
        session_id=req.session_id,
        source="llm",
        knowledge_sources=knowledge_sources or None,
    )


@app.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """SSE 스트리밍 엔드포인트 — 프론트에서 EventSource 또는 fetch + ReadableStream으로 소비"""
    client: AsyncOpenAI = app.state.llm_client
    user_prompt = latest_user_prompt(req.messages)
    company_context, knowledge_sources = await load_company_context(user_prompt, settings)

    async def token_generator() -> AsyncIterator[str]:
        if settings.crewai_enabled and should_route_to_crewai(user_prompt):
            try:
                crew_report, crew_graph = await run_crewai_report(
                    user_prompt,
                    settings,
                    company_context,
                )
                yield f"data: {json.dumps({'source': 'crewai', 'crew_graph': crew_graph, 'knowledge_sources': knowledge_sources, 'token': ''}, ensure_ascii=False)}\n\n"
                for idx in range(0, len(crew_report), 140):
                    chunk = crew_report[idx : idx + 140]
                    if chunk:
                        yield f"data: {json.dumps({'token': chunk}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return
            except Exception as exc:
                print(f"⚠️ CrewAI failed in /chat/stream, using default LLM fallback: {exc}")

        yield f"data: {json.dumps({'source': 'llm', 'knowledge_sources': knowledge_sources, 'token': ''}, ensure_ascii=False)}\n\n"
        stream = await client.chat.completions.create(
            model=settings.llm_model,
            messages=inject_company_context(req.messages, company_context),
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                # SSE payload is JSON-encoded to preserve newlines and special chars.
                yield f"data: {json.dumps({'token': delta}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        token_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )
