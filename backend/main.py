from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import json
from typing import Literal

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel, Field, field_validator

from config import Settings, get_settings


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

    app = FastAPI(title="OpenClaw Gateway", lifespan=lifespan)

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

    completion = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[{"role": m.role, "content": m.content} for m in req.messages],
    )

    reply = completion.choices[0].message.content or ""
    return ChatResponse(message=reply, session_id=req.session_id)


@app.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """SSE 스트리밍 엔드포인트 — 프론트에서 EventSource 또는 fetch + ReadableStream으로 소비"""
    client: AsyncOpenAI = app.state.llm_client

    async def token_generator() -> AsyncIterator[str]:
        stream = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": m.role, "content": m.content} for m in req.messages],
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
