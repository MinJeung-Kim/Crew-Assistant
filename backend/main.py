from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import asyncio
import json
from typing import Literal

from fastapi import FastAPI, Depends
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


# ─── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.llm_client = AsyncOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
    )
    print(f"✅ LLM client ready  model={settings.llm_model}  url={settings.llm_base_url}")
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


def serialize_messages(messages: list[ChatMessage]) -> list[dict[str, str]]:
    return [{"role": m.role, "content": m.content} for m in messages]


def latest_user_prompt(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return messages[-1].content


async def run_default_llm_chat(
    client: AsyncOpenAI,
    settings: Settings,
    messages: list[ChatMessage],
) -> str:
    completion = await client.chat.completions.create(
        model=settings.llm_model,
        messages=serialize_messages(messages),
    )
    return completion.choices[0].message.content or ""


async def run_crewai_report(
    user_prompt: str,
    settings: Settings,
) -> tuple[str, dict[str, object]]:
    runtime = CrewRuntimeConfig(
        llm_model=settings.llm_model,
        llm_base_url=settings.llm_base_url,
        llm_api_key=settings.llm_api_key,
        crewai_model=settings.crewai_model,
        web_search_results=settings.crewai_web_search_results,
    )
    execution = await asyncio.to_thread(
        run_dynamic_research_crew_with_trace,
        user_prompt,
        runtime,
    )
    return execution.report, crew_graph_to_dict(execution.graph)


# ─── Routes ───────────────────────────────────────────────────────────────────
@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    client: AsyncOpenAI = app.state.llm_client
    user_prompt = latest_user_prompt(req.messages)

    if settings.crewai_enabled and should_route_to_crewai(user_prompt):
        try:
            reply, crew_graph = await run_crewai_report(user_prompt, settings)
            return ChatResponse(
                message=reply,
                session_id=req.session_id,
                source="crewai",
                crew_graph=crew_graph,
            )
        except Exception as exc:
            print(f"⚠️ CrewAI failed in /chat, using default LLM fallback: {exc}")

    reply = await run_default_llm_chat(client, settings, req.messages)
    return ChatResponse(message=reply, session_id=req.session_id, source="llm")


@app.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """SSE 스트리밍 엔드포인트 — 프론트에서 EventSource 또는 fetch + ReadableStream으로 소비"""
    client: AsyncOpenAI = app.state.llm_client
    user_prompt = latest_user_prompt(req.messages)

    async def token_generator() -> AsyncIterator[str]:
        if settings.crewai_enabled and should_route_to_crewai(user_prompt):
            try:
                crew_report, crew_graph = await run_crewai_report(user_prompt, settings)
                yield f"data: {json.dumps({'source': 'crewai', 'crew_graph': crew_graph, 'token': ''}, ensure_ascii=False)}\n\n"
                for idx in range(0, len(crew_report), 140):
                    chunk = crew_report[idx : idx + 140]
                    if chunk:
                        yield f"data: {json.dumps({'token': chunk}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return
            except Exception as exc:
                print(f"⚠️ CrewAI failed in /chat/stream, using default LLM fallback: {exc}")

        yield f"data: {json.dumps({'source': 'llm', 'token': ''}, ensure_ascii=False)}\n\n"
        stream = await client.chat.completions.create(
            model=settings.llm_model,
            messages=serialize_messages(req.messages),
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
