from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import httpx

from config import Settings
from knowledge_base import extract_text_from_upload
from onboarding_workflow import (
    DRIVE_SCOPE_HINTS,
    fetch_google_token_scopes,
    has_any_required_scope,
    looks_like_google_oauth_token,
)

SEARCH_TERM_PATTERN = re.compile(r"[a-z0-9\uac00-\ud7a3]{2,}", re.IGNORECASE)
GOOGLE_EXPORT_TEXT_MIME = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.presentation": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
}
DIRECT_DOWNLOAD_MIME_ALLOWLIST = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
DIRECT_DOWNLOAD_SUFFIX_ALLOWLIST = {
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".json",
    ".pdf",
    ".docx",
}


def extract_search_terms(query: str, max_terms: int = 4) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    for match in SEARCH_TERM_PATTERN.finditer(query.lower()):
        term = match.group(0).strip()
        if not term or term in seen:
            continue
        seen.add(term)
        terms.append(term)
        if len(terms) >= max_terms:
            break

    return terms


def _escape_drive_query_token(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def build_drive_search_query(query: str, max_terms: int = 4) -> str:
    terms = extract_search_terms(query, max_terms=max_terms)
    if not terms:
        return "trashed = false"

    clauses: list[str] = []
    for term in terms:
        escaped = _escape_drive_query_token(term)
        clauses.append(f"name contains '{escaped}'")
        clauses.append(f"fullText contains '{escaped}'")

    return f"trashed = false and ({' or '.join(clauses)})"


def _extract_text_from_drive_bytes(filename: str, mime_type: str, payload: bytes) -> str:
    normalized_mime = (mime_type or "").strip().lower()
    suffix = Path(filename).suffix.lower()

    if normalized_mime.startswith("text/") or suffix in {".txt", ".md", ".markdown", ".csv", ".json"}:
        for encoding in ("utf-8", "utf-8-sig", "cp949", "euc-kr", "latin-1"):
            try:
                return payload.decode(encoding)
            except UnicodeDecodeError:
                continue
        return payload.decode("utf-8", errors="ignore")

    return extract_text_from_upload(filename, payload)


def _build_excerpt(text: str, max_chars: int) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return ""

    if len(normalized) <= max_chars:
        return normalized

    return normalized[:max_chars].rstrip() + "..."


async def _search_drive_files(
    http_client: httpx.AsyncClient,
    *,
    access_token: str,
    query: str,
    max_results: int,
) -> tuple[list[dict[str, Any]], str | None]:
    params = {
        "q": build_drive_search_query(query),
        "fields": "files(id,name,mimeType,modifiedTime,webViewLink)",
        "orderBy": "modifiedTime desc",
        "pageSize": str(max_results),
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }

    try:
        response = await http_client.get(
            "https://www.googleapis.com/drive/v3/files",
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    except Exception as exc:
        return [], f"Google Drive search request failed: {exc}"

    if response.status_code >= 400:
        return [], f"Google Drive search failed: HTTP {response.status_code}"

    try:
        payload = response.json()
    except Exception:
        return [], "Google Drive search response parse failed"

    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(files, list):
        return [], None

    normalized: list[dict[str, Any]] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "id": str(item.get("id", "")).strip(),
                "name": str(item.get("name", "Untitled")).strip() or "Untitled",
                "mime_type": str(item.get("mimeType", "")).strip().lower(),
                "web_view_link": str(item.get("webViewLink", "")).strip(),
                "modified_time": str(item.get("modifiedTime", "")).strip(),
            }
        )

    return normalized, None


async def _download_drive_file_text(
    http_client: httpx.AsyncClient,
    *,
    access_token: str,
    file_id: str,
    file_name: str,
    mime_type: str,
    max_file_bytes: int,
) -> str:
    if mime_type == "application/vnd.google-apps.folder":
        return ""

    headers = {"Authorization": f"Bearer {access_token}"}
    request_url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
    request_params: dict[str, str] = {"alt": "media"}

    export_mime = GOOGLE_EXPORT_TEXT_MIME.get(mime_type)
    if export_mime:
        request_url = f"https://www.googleapis.com/drive/v3/files/{file_id}/export"
        request_params = {"mimeType": export_mime}
    else:
        suffix = Path(file_name).suffix.lower()
        if (
            mime_type not in DIRECT_DOWNLOAD_MIME_ALLOWLIST
            and suffix not in DIRECT_DOWNLOAD_SUFFIX_ALLOWLIST
        ):
            return ""

    response = await http_client.get(request_url, params=request_params, headers=headers)
    if response.status_code >= 400:
        return ""

    payload = response.content
    if not payload:
        return ""
    if len(payload) > max_file_bytes:
        return ""

    try:
        filename_for_parser = file_name
        if export_mime == "text/plain" and not Path(file_name).suffix:
            filename_for_parser = f"{file_name}.txt"
        elif export_mime == "text/csv" and not Path(file_name).suffix:
            filename_for_parser = f"{file_name}.csv"

        return _extract_text_from_drive_bytes(filename_for_parser, mime_type, payload)
    except Exception:
        return ""


async def build_google_drive_context(
    *,
    query: str,
    settings: Settings,
    google_api_key: str,
) -> tuple[str, list[dict[str, object]], str | None]:
    if not settings.google_drive_context_enabled:
        return "", [], None

    access_token = google_api_key.strip()
    if not access_token:
        return "", [], None

    if not looks_like_google_oauth_token(access_token):
        return "", [], "Google Drive shared file context requires OAuth token (ya29...)."

    scopes, scope_error = await fetch_google_token_scopes(access_token)
    if scope_error:
        return "", [], scope_error

    if scopes and not has_any_required_scope(scopes, DRIVE_SCOPE_HINTS):
        return (
            "",
            [],
            "Google OAuth token missing Drive scope for shared file access.",
        )

    async with httpx.AsyncClient(timeout=20) as http_client:
        files, search_error = await _search_drive_files(
            http_client,
            access_token=access_token,
            query=query,
            max_results=settings.google_drive_context_results,
        )

        if search_error:
            return "", [], search_error
        if not files:
            return "", [], None

        context_parts: list[str] = []
        sources: list[dict[str, object]] = []

        for index, file_info in enumerate(files, start=1):
            file_id = str(file_info.get("id", "")).strip()
            file_name = str(file_info.get("name", "Untitled"))
            mime_type = str(file_info.get("mime_type", ""))
            web_view_link = str(file_info.get("web_view_link", ""))

            if not file_id:
                continue

            text = await _download_drive_file_text(
                http_client,
                access_token=access_token,
                file_id=file_id,
                file_name=file_name,
                mime_type=mime_type,
                max_file_bytes=settings.google_drive_context_max_file_bytes,
            )
            excerpt = _build_excerpt(text, settings.google_drive_context_max_chars)
            if not excerpt:
                continue

            header = f"[Drive Source {index}] {file_name}"
            if web_view_link:
                header = f"{header}\nLink: {web_view_link}"

            context_parts.append(f"{header}\n{excerpt}")
            sources.append(
                {
                    "id": file_id,
                    "document_name": file_name,
                    "chunk_index": 0,
                    "type": "google_drive",
                    "mime_type": mime_type,
                    "web_view_link": web_view_link or None,
                    "modified_time": str(file_info.get("modified_time", "")) or None,
                }
            )

    if not context_parts:
        return "", [], None

    return "\n\n".join(context_parts), sources, None
