from __future__ import annotations

from collections.abc import Iterator
import json


def format_sse_payload(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def done_sse_payload() -> str:
    return "data: [DONE]\n\n"


def iter_text_chunks(text: str, chunk_size: int = 140) -> Iterator[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    for idx in range(0, len(text), chunk_size):
        chunk = text[idx : idx + chunk_size]
        if chunk:
            yield chunk
