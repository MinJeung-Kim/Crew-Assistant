from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from io import BytesIO
import importlib
import json
import math
from pathlib import Path
import re
from typing import Any

from openai import AsyncOpenAI


@dataclass
class KnowledgeChunk:
    id: str
    document_name: str
    chunk_index: int
    text: str
    embedding: list[float] | None = None


class CompanyKnowledgeBase:
    def __init__(self, storage_path: str) -> None:
        self.storage_dir = Path(storage_path)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.storage_dir / "company_knowledge.json"
        self._lock = asyncio.Lock()

        self.chunks: list[KnowledgeChunk] = []
        self.updated_at: str | None = None
        self._load_from_disk()

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    @property
    def documents(self) -> list[str]:
        return sorted({chunk.document_name for chunk in self.chunks})

    def status(self) -> dict[str, object]:
        return {
            "documents": self.documents,
            "chunk_count": self.chunk_count,
            "updated_at": self.updated_at,
        }

    async def ingest_document(
        self,
        document_name: str,
        text: str,
        client: AsyncOpenAI,
        embedding_model: str,
        max_chunk_chars: int,
        chunk_overlap: int,
    ) -> dict[str, object]:
        normalized_text = normalize_text(text)
        chunk_texts = split_text(normalized_text, max_chunk_chars, chunk_overlap)
        if not chunk_texts:
            raise ValueError("No readable text found in document")

        embeddings = await embed_texts(client, embedding_model, chunk_texts)

        base_id = slugify(Path(document_name).stem or document_name)
        new_chunks = [
            KnowledgeChunk(
                id=f"{base_id}-{index + 1}",
                document_name=document_name,
                chunk_index=index,
                text=chunk_text,
                embedding=embeddings[index] if embeddings else None,
            )
            for index, chunk_text in enumerate(chunk_texts)
        ]

        async with self._lock:
            self.chunks = [
                existing
                for existing in self.chunks
                if existing.document_name != document_name
            ]
            self.chunks.extend(new_chunks)
            self.updated_at = utc_now_iso()
            self._save_to_disk()

        return {
            "document_name": document_name,
            "chunk_count": len(new_chunks),
            "embedded": embeddings is not None,
            "updated_at": self.updated_at,
            "documents": self.documents,
            "total_chunks": self.chunk_count,
        }

    async def build_context(
        self,
        query: str,
        client: AsyncOpenAI,
        embedding_model: str,
        top_k: int,
    ) -> tuple[str, list[dict[str, object]]]:
        if not self.chunks:
            return "", []

        chunks = await self.retrieve(query, client, embedding_model, top_k)
        if not chunks:
            return "", []

        sources: list[dict[str, object]] = []
        context_parts: list[str] = []

        for index, chunk in enumerate(chunks, start=1):
            excerpt = chunk.text.strip()
            if len(excerpt) > 1400:
                excerpt = excerpt[:1400].rstrip() + "..."

            source_info = {
                "id": chunk.id,
                "document_name": chunk.document_name,
                "chunk_index": chunk.chunk_index,
            }
            sources.append(source_info)
            context_parts.append(
                f"[Source {index}] {chunk.document_name} (chunk {chunk.chunk_index + 1})\n{excerpt}"
            )

        return "\n\n".join(context_parts), sources

    async def retrieve(
        self,
        query: str,
        client: AsyncOpenAI,
        embedding_model: str,
        top_k: int,
    ) -> list[KnowledgeChunk]:
        if not self.chunks:
            return []

        snapshot = list(self.chunks)
        query_embedding = await embed_query(client, embedding_model, query)
        use_vector_search = bool(
            query_embedding and all(chunk.embedding is not None for chunk in snapshot)
        )

        scored: list[tuple[float, KnowledgeChunk]] = []
        if use_vector_search and query_embedding is not None:
            for chunk in snapshot:
                vector = chunk.embedding or []
                score = cosine_similarity(query_embedding, vector)
                scored.append((score, chunk))
        else:
            for chunk in snapshot:
                score = lexical_score(query, chunk.text)
                scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)

        selected = [chunk for score, chunk in scored if score > 0][:top_k]
        if selected:
            return selected

        return [chunk for _, chunk in scored[:top_k]]

    def _load_from_disk(self) -> None:
        if not self.index_path.exists():
            return

        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            loaded_chunks = payload.get("chunks", [])
            self.chunks = [
                KnowledgeChunk(
                    id=str(item.get("id", "")),
                    document_name=str(item.get("document_name", "")),
                    chunk_index=int(item.get("chunk_index", 0)),
                    text=str(item.get("text", "")),
                    embedding=
                        [float(value) for value in item.get("embedding", [])]
                        if isinstance(item.get("embedding"), list)
                        else None,
                )
                for item in loaded_chunks
                if isinstance(item, dict)
            ]
            self.updated_at = (
                str(payload.get("updated_at"))
                if payload.get("updated_at") is not None
                else None
            )
        except Exception as exc:
            print(f"⚠️ Failed to load knowledge index: {exc}")
            self.chunks = []
            self.updated_at = None

    def _save_to_disk(self) -> None:
        payload: dict[str, Any] = {
            "updated_at": self.updated_at,
            "chunks": [asdict(chunk) for chunk in self.chunks],
        }
        self.index_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def extract_text_from_upload(filename: str, content: bytes) -> str:
    extension = Path(filename).suffix.lower()

    if extension in {".txt", ".md", ".markdown", ".csv", ".json"}:
        return decode_text_bytes(content)

    if extension == ".pdf":
        try:
            pypdf_module = importlib.import_module("pypdf")
            pdf_reader_cls = getattr(pypdf_module, "PdfReader")
        except Exception as exc:
            raise ValueError("PDF parsing requires pypdf package") from exc

        reader = pdf_reader_cls(BytesIO(content))
        page_texts = [(page.extract_text() or "").strip() for page in reader.pages]
        return "\n\n".join(text for text in page_texts if text)

    if extension == ".docx":
        try:
            docx_module = importlib.import_module("docx")
            document_cls = getattr(docx_module, "Document")
        except Exception as exc:
            raise ValueError("DOCX parsing requires python-docx package") from exc

        doc = document_cls(BytesIO(content))
        paragraphs = [paragraph.text.strip() for paragraph in doc.paragraphs]
        return "\n\n".join(text for text in paragraphs if text)

    # Fallback for unknown extensions.
    return decode_text_bytes(content)


async def embed_texts(
    client: AsyncOpenAI,
    model: str,
    texts: list[str],
) -> list[list[float]] | None:
    if not model.strip() or not texts:
        return None

    try:
        response = await client.embeddings.create(
            model=model,
            input=texts,
        )
    except Exception as exc:
        print(f"⚠️ Embedding generation failed, fallback to lexical retrieval: {exc}")
        return None

    vectors = [
        row.embedding
        for row in sorted(response.data, key=lambda item: item.index)
        if row.embedding
    ]
    if len(vectors) != len(texts):
        return None

    return vectors


async def embed_query(
    client: AsyncOpenAI,
    model: str,
    query: str,
) -> list[float] | None:
    if not model.strip() or not query.strip():
        return None

    vectors = await embed_texts(client, model, [query])
    if not vectors:
        return None
    return vectors[0]


def normalize_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def split_text(text: str, max_chars: int, overlap: int) -> list[str]:
    if not text:
        return []

    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"

        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        if len(paragraph) <= max_chars:
            current = paragraph
            continue

        start = 0
        while start < len(paragraph):
            end = min(start + max_chars, len(paragraph))
            piece = paragraph[start:end].strip()
            if piece:
                chunks.append(piece)
            if end >= len(paragraph):
                break
            start = max(0, end - overlap)

    if current:
        chunks.append(current)

    return chunks


def decode_text_bytes(content: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp949", "euc-kr", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")


def lexical_score(query: str, text: str) -> float:
    query_terms = tokenize(query)
    text_terms = tokenize(text)
    if not query_terms or not text_terms:
        return 0.0

    text_set = set(text_terms)
    overlap = sum(1 for term in query_terms if term in text_set)
    return overlap / max(len(query_terms), 1)


def tokenize(value: str) -> list[str]:
    return re.findall(r"[a-z0-9가-힣]{2,}", value.lower())


def cosine_similarity(vector_a: list[float], vector_b: list[float]) -> float:
    if not vector_a or not vector_b or len(vector_a) != len(vector_b):
        return 0.0

    dot = sum(a * b for a, b in zip(vector_a, vector_b))
    norm_a = math.sqrt(sum(a * a for a in vector_a))
    norm_b = math.sqrt(sum(b * b for b in vector_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


def slugify(value: str) -> str:
    collapsed = re.sub(r"\s+", "-", value.strip().lower())
    cleaned = re.sub(r"[^a-z0-9가-힣_-]", "", collapsed)
    return cleaned or "doc"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
