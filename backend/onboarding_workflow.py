from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
import html
import re
from typing import Any, Callable

import httpx
from openai import AsyncOpenAI

from config import Settings


BRACKETED_PROFILE_PATTERN = re.compile(
    r"^\s*\[(?P<name>[^\]]+)\]\s*\[(?P<department>[^\]]+)\]\s*\[(?P<join_date>[^\]]+)\]\s*\[(?P<email>[^\]]+)\]\s*$"
)
PLAIN_PROFILE_PATTERN = re.compile(
    r"^\s*(?P<name>\S+)\s+(?P<department>\S+)\s+(?P<join_date>\d{4}[-/.]\d{1,2}[-/.]\d{1,2})\s+(?P<email>[^\s@]+@[^\s@]+\.[^\s@]+)\s*$"
)

DRIVE_SCOPE_HINTS = (
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/drive",
)

GMAIL_SCOPE_HINTS = (
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://mail.google.com/",
)

URL_PATTERN = re.compile(r"(https?://[^\s<>()]+)")
NUMBERED_SECTION_PATTERN = re.compile(r"^\s*\d+\)\s+(.+)$")
SLACK_TOKEN_EXACT_PATTERN = re.compile(
    r"^(xox[pb]-[A-Za-z0-9-]{10,}|xoxa-2-[A-Za-z0-9-]{10,})$"
)
SLACK_TOKEN_SEARCH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9-])((?:xox[pb]-[A-Za-z0-9-]{10,}|xoxa-2-[A-Za-z0-9-]{10,}))(?![A-Za-z0-9-])"
)
SLACK_SHARED_INVITE_EXACT_PATTERN = re.compile(
    r"^https://join\.slack\.com/t/[A-Za-z0-9_-]+/shared_invite/[A-Za-z0-9~_-]+$"
)
SLACK_SHARED_INVITE_SEARCH_PATTERN = re.compile(
    r"(https://join\.slack\.com/t/[A-Za-z0-9_-]+/shared_invite/[A-Za-z0-9~_-]+)"
)


@dataclass
class OnboardingProfile:
    name: str
    department: str
    join_date: str
    email: str


@dataclass
class IntegrationSecrets:
    google_api_key: str = ""
    slack_api_key: str = ""
    slack_invite_link: str = ""
    updated_at: str | None = None


@dataclass
class OnboardingWorkflowResult:
    report: str
    email_sent: bool
    email_detail: str
    slack_invited: bool
    slack_detail: str
    matched_files: list[dict[str, Any]]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mask_secret(secret: str) -> str | None:
    raw = secret.strip()
    if not raw:
        return None
    if len(raw) <= 8:
        return "*" * len(raw)
    return f"{raw[:4]}...{raw[-3:]}"


def parse_onboarding_profile(prompt: str) -> OnboardingProfile | None:
    text = prompt.strip()

    match = BRACKETED_PROFILE_PATTERN.match(text)
    if not match:
        match = PLAIN_PROFILE_PATTERN.match(text)

    if not match:
        return None

    name = match.group("name").strip()
    department = match.group("department").strip()
    join_date = normalize_join_date(match.group("join_date").strip())
    email = match.group("email").strip()

    if not name or not department or not join_date or not is_valid_email(email):
        return None

    return OnboardingProfile(
        name=name,
        department=department,
        join_date=join_date,
        email=email,
    )


def normalize_join_date(raw_value: str) -> str:
    normalized = raw_value.strip().replace(".", "-").replace("/", "-")
    if not re.match(r"^\d{4}-\d{1,2}-\d{1,2}$", normalized):
        return ""

    try:
        year, month, day = [int(part) for part in normalized.split("-")]
        return datetime(year, month, day).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def is_valid_email(value: str) -> bool:
    return re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", value) is not None


def looks_like_google_oauth_token(raw_value: str) -> bool:
    stripped = raw_value.strip()
    return stripped.startswith("ya29.") or stripped.startswith("ya29")


def looks_like_slack_token(raw_value: str) -> bool:
    stripped = raw_value.strip()
    return SLACK_TOKEN_EXACT_PATTERN.fullmatch(stripped) is not None


def extract_slack_token(prompt: str) -> str | None:
    match = SLACK_TOKEN_SEARCH_PATTERN.search(prompt.strip())
    if not match:
        return None
    return match.group(1)


def looks_like_slack_invite_link(raw_value: str) -> bool:
    return SLACK_SHARED_INVITE_EXACT_PATTERN.fullmatch(raw_value.strip()) is not None


def extract_slack_invite_link(prompt: str) -> str | None:
    match = SLACK_SHARED_INVITE_SEARCH_PATTERN.search(prompt.strip())
    if not match:
        return None
    return match.group(1)


def is_slack_bot_token(raw_value: str) -> bool:
    return raw_value.strip().startswith("xoxb-")


def looks_like_slack_bot_token(raw_value: str) -> bool:
    return is_slack_bot_token(raw_value) and looks_like_slack_token(raw_value)


def extract_slack_bot_token(prompt: str) -> str | None:
    token = extract_slack_token(prompt)
    if not token or not is_slack_bot_token(token):
        return None
    return token


def parse_scope_string(scope_raw: str | None) -> set[str]:
    if not isinstance(scope_raw, str):
        return set()
    return {scope.strip() for scope in scope_raw.split(" ") if scope.strip()}


def has_any_required_scope(granted: set[str], required: tuple[str, ...]) -> bool:
    if not granted:
        return False
    return any(scope in granted for scope in required)


def format_scope_list(scopes: tuple[str, ...] | set[str]) -> str:
    if isinstance(scopes, set):
        values = sorted(scopes)
    else:
        values = list(scopes)
    return ", ".join(values)


async def fetch_google_token_scopes(token: str) -> tuple[set[str], str | None]:
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            response = await http.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"access_token": token},
            )
    except Exception as exc:
        return set(), f"tokeninfo request failed: {exc}"

    if response.status_code >= 400:
        return set(), f"tokeninfo HTTP {response.status_code}"

    try:
        payload = response.json()
    except Exception:
        return set(), "tokeninfo response parse failed"

    if not isinstance(payload, dict):
        return set(), "tokeninfo response is not JSON object"

    return parse_scope_string(payload.get("scope")), None


def _extract_email_from_payload(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None

    raw_email = payload.get("email")
    if not isinstance(raw_email, str):
        return None

    normalized = raw_email.strip().lower()
    if not normalized or not is_valid_email(normalized):
        return None
    return normalized


async def fetch_google_authenticated_email(token: str) -> tuple[str | None, str | None]:
    access_token = token.strip()
    if not access_token:
        return None, "Google API key is not configured."
    if not looks_like_google_oauth_token(access_token):
        return None, "Google key is API key format. OAuth token is required."

    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        async with httpx.AsyncClient(timeout=15) as http:
            userinfo_response = await http.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers=headers,
            )
    except Exception as exc:
        return None, f"userinfo request failed: {exc}"

    if userinfo_response.status_code < 400:
        try:
            userinfo_payload = userinfo_response.json()
        except Exception:
            userinfo_payload = None
        email = _extract_email_from_payload(userinfo_payload)
        if email:
            return email, None

    try:
        async with httpx.AsyncClient(timeout=15) as http:
            tokeninfo_response = await http.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"access_token": access_token},
            )
    except Exception as exc:
        return None, f"tokeninfo request failed: {exc}"

    if tokeninfo_response.status_code >= 400:
        return None, f"tokeninfo HTTP {tokeninfo_response.status_code}"

    try:
        tokeninfo_payload = tokeninfo_response.json()
    except Exception:
        return None, "tokeninfo response parse failed"

    email = _extract_email_from_payload(tokeninfo_payload)
    if email:
        return email, None

    return None, "authenticated Google account email not found in OAuth profile"


def extract_google_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        return ""

    if not isinstance(payload, dict):
        return ""

    error_value = payload.get("error")
    if isinstance(error_value, str):
        return error_value

    if not isinstance(error_value, dict):
        return ""

    message = str(error_value.get("message", "")).strip()
    reasons: list[str] = []
    errors = error_value.get("errors")
    if isinstance(errors, list):
        for item in errors:
            if not isinstance(item, dict):
                continue
            reason = str(item.get("reason", "")).strip()
            if reason:
                reasons.append(reason)

    if reasons and message:
        return f"{message} (reason: {', '.join(sorted(set(reasons)))})"
    if reasons:
        return f"reason: {', '.join(sorted(set(reasons)))}"
    return message


def build_google_http_error_detail(
    *,
    prefix: str,
    response: httpx.Response,
    required_scopes: tuple[str, ...] | None = None,
    granted_scopes: set[str] | None = None,
    token_scope_error: str | None = None,
) -> str:
    message = extract_google_error_message(response)
    detail_parts = [f"{prefix}: HTTP {response.status_code}"]

    if message:
        detail_parts.append(message)

    if token_scope_error:
        detail_parts.append(token_scope_error)

    if required_scopes is not None:
        detail_parts.append(f"required scopes: {format_scope_list(required_scopes)}")

    if granted_scopes is not None:
        if granted_scopes:
            detail_parts.append(f"granted scopes: {format_scope_list(granted_scopes)}")
        else:
            detail_parts.append("granted scopes: unavailable")

    return " | ".join(detail_parts)


def _escape_drive_query_token(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def build_drive_query(profile: OnboardingProfile) -> str:
    keywords = [
        "onboarding",
        "입사",
        "서류",
        "가이드",
        profile.department,
        profile.name,
    ]
    keyword_terms = [
        f"name contains '{_escape_drive_query_token(keyword)}'"
        for keyword in keywords
        if keyword.strip()
    ]
    if not keyword_terms:
        keyword_terms = ["name contains 'onboarding'"]

    return f"trashed = false and ({' or '.join(keyword_terms)})"


async def search_google_drive_files(
    profile: OnboardingProfile,
    settings: Settings,
    secrets: IntegrationSecrets,
) -> tuple[list[dict[str, Any]], str | None]:
    google_key = secrets.google_api_key.strip()
    if not google_key:
        return [], "Google API key is not configured."

    params = {
        "q": build_drive_query(profile),
        "fields": "files(id,name,mimeType,modifiedTime,webViewLink,owners(displayName,emailAddress))",
        "orderBy": "modifiedTime desc",
        "pageSize": str(settings.onboarding_drive_file_limit),
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }

    headers: dict[str, str] = {}
    oauth_scopes: set[str] | None = None
    token_scope_error: str | None = None
    if looks_like_google_oauth_token(google_key):
        headers["Authorization"] = f"Bearer {google_key}"
        oauth_scopes, token_scope_error = await fetch_google_token_scopes(google_key)
        if oauth_scopes and not has_any_required_scope(oauth_scopes, DRIVE_SCOPE_HINTS):
            return (
                [],
                (
                    "Google OAuth token missing Drive scope. "
                    f"required scopes: {format_scope_list(DRIVE_SCOPE_HINTS)} | "
                    f"granted scopes: {format_scope_list(oauth_scopes)}"
                ),
            )
    else:
        params["key"] = google_key

    try:
        async with httpx.AsyncClient(timeout=20) as http:
            response = await http.get(
                "https://www.googleapis.com/drive/v3/files",
                params=params,
                headers=headers,
            )
    except Exception as exc:
        return [], f"Google Drive request failed: {exc}"

    if response.status_code >= 400:
        detail = build_google_http_error_detail(
            prefix="Google Drive request failed",
            response=response,
            required_scopes=DRIVE_SCOPE_HINTS if headers.get("Authorization") else None,
            granted_scopes=oauth_scopes,
            token_scope_error=token_scope_error,
        )
        if response.status_code == 403 and not headers.get("Authorization"):
            detail += " | If using API key, verify Drive API is enabled and key restrictions allow Drive v3 requests"
        return [], detail

    try:
        payload = response.json()
    except Exception:
        return [], "Google Drive response could not be parsed as JSON."

    files = payload.get("files")
    if not isinstance(files, list):
        return [], None

    normalized: list[dict[str, Any]] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "id": str(item.get("id", "")),
                "name": str(item.get("name", "Untitled")),
                "mime_type": str(item.get("mimeType", "")),
                "modified_time": str(item.get("modifiedTime", "")),
                "web_view_link": str(item.get("webViewLink", "")),
            }
        )
    return normalized, None


def render_file_list(files: list[dict[str, Any]]) -> str:
    if not files:
        return "- 관련 파일을 찾지 못했습니다."

    lines: list[str] = []
    for index, item in enumerate(files, start=1):
        name = str(item.get("name", "Untitled"))
        modified = str(item.get("modified_time", ""))
        link = str(item.get("web_view_link", ""))
        modified_label = f" ({modified})" if modified else ""
        link_label = f" - {link}" if link else ""
        lines.append(f"- {index}. {name}{modified_label}{link_label}")
    return "\n".join(lines)


async def generate_onboarding_summary(
    client: AsyncOpenAI,
    settings: Settings,
    profile: OnboardingProfile,
    files: list[dict[str, Any]],
    drive_error: str | None,
    hr_contact_email: str | None = None,
) -> str:
    file_list = render_file_list(files)
    error_context = f"\nDrive Error: {drive_error}" if drive_error else ""
    hr_contact = (hr_contact_email or "").strip()
    hr_contact_context = hr_contact if hr_contact else "not_available"

    completion = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an HR onboarding coordinator. "
                    "Write concise Korean onboarding email summary using the provided employee profile and file list. "
                    "Return sections: 1) 입사 서류 요약 2) 온보딩 파일 요약 3) 첫 주 체크리스트. "
                    "If HR contact email is provided, always use that email as the only HR contact. "
                    "Never use employee email as HR contact email."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Employee: {profile.name}\n"
                    f"Department: {profile.department}\n"
                    f"Join Date: {profile.join_date}\n"
                    f"Email: {profile.email}\n\n"
                    f"HR Contact Email: {hr_contact_context}\n\n"
                    f"Drive Files:\n{file_list}{error_context}"
                ),
            },
        ],
    )

    content = (completion.choices[0].message.content or "").strip()
    if content:
        return content

    return (
        "1) 입사 서류 요약\n"
        "- 신규 입사자에게 필요한 기본 서류를 준비해 주세요.\n\n"
        "2) 온보딩 파일 요약\n"
        f"{file_list}\n\n"
        "3) 첫 주 체크리스트\n"
        "- 계정 발급, 보안교육, 팀 온보딩 미팅을 순서대로 진행합니다.\n"
        + (
            f"- 문의 연락처(HR): {hr_contact}\n"
            if hr_contact
            else ""
        )
    )


def build_email_subject(profile: OnboardingProfile) -> str:
    return f"[온보딩 안내] {profile.name} 님 입사 준비 자료 안내"


def build_email_body(
    profile: OnboardingProfile,
    summary: str,
    hr_contact_email: str | None = None,
    slack_invite_link: str | None = None,
) -> str:
    hr_contact = (hr_contact_email or "").strip()
    invite_link_raw = (slack_invite_link or "").strip()
    invite_block = (
        "Slack 워크스페이스 초대 링크\n"
        f"- {invite_link_raw}\n"
        "링크를 열어 Slack 워크스페이스에 참여해 주세요.\n\n"
        if looks_like_slack_invite_link(invite_link_raw)
        else ""
    )
    contact_line = (
        f"문의사항이 있으면 HR/IT 담당자({hr_contact})에게 편하게 연락 부탁드립니다.\n"
        if hr_contact
        else "문의사항이 있으면 HR/IT 담당자에게 편하게 연락 부탁드립니다.\n"
    )

    return (
        f"안녕하세요 {profile.name} 님,\n\n"
        f"{profile.department} 입사를 환영합니다. (입사일: {profile.join_date})\n"
        "아래에 입사 서류와 온보딩 자료 요약을 전달드립니다.\n\n"
        f"{summary}\n\n"
        f"{invite_block}"
        f"{contact_line}"
        "감사합니다."
    )


def _normalize_summary_markdown(summary: str) -> str:
    normalized = summary.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return ""

    lines: list[str] = []
    for raw_line in normalized.split("\n"):
        match = NUMBERED_SECTION_PATTERN.match(raw_line)
        if match:
            lines.append(f"### {match.group(1).strip()}")
            continue

        def _url_to_markdown_link(url_match: re.Match[str]) -> str:
            url = url_match.group(1)
            return f"[{url}]({url})"

        line_with_links = URL_PATTERN.sub(_url_to_markdown_link, raw_line)
        lines.append(line_with_links)

    return "\n".join(lines)


def _style_rendered_markdown_html(markdown_html: str) -> str:
    styled = markdown_html
    replacements = {
        "<p>": "<p style=\"margin:0 0 12px; color:#111827; line-height:1.75;\">",
        "<ul>": "<ul style=\"margin:0 0 14px; padding-left:20px; color:#111827; line-height:1.65;\">",
        "<ol>": "<ol style=\"margin:0 0 14px; padding-left:20px; color:#111827; line-height:1.65;\">",
        "<li>": "<li style=\"margin:0 0 6px;\">",
        "<blockquote>": "<blockquote style=\"margin:0 0 14px; padding:10px 12px; border-left:3px solid #93c5fd; background:#eff6ff; color:#1e3a8a;\">",
        "<pre>": "<pre style=\"margin:0 0 14px; padding:12px; background:#0f172a; color:#e5e7eb; border-radius:10px; overflow:auto; font-size:12px; line-height:1.6;\">",
        "<code>": "<code style=\"font-family:Consolas,'Courier New',monospace;\">",
        "<table>": "<table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"border-collapse:collapse; margin:0 0 14px; font-size:13px; color:#111827;\">",
        "<th>": "<th style=\"border:1px solid #d1d5db; padding:8px 10px; background:#f8fafc; text-align:left;\">",
        "<td>": "<td style=\"border:1px solid #d1d5db; padding:8px 10px; vertical-align:top;\">",
        "<hr>": "<hr style=\"border:none; border-top:1px solid #e5e7eb; margin:14px 0;\">",
        "<hr />": "<hr style=\"border:none; border-top:1px solid #e5e7eb; margin:14px 0;\">",
        "<h1>": "<h1 style=\"margin:18px 0 10px; font-size:20px; color:#0f172a;\">",
        "<h2>": "<h2 style=\"margin:18px 0 10px; font-size:18px; color:#0f172a;\">",
        "<h3>": "<h3 style=\"margin:18px 0 10px; font-size:16px; color:#0f172a;\">",
        "<h4>": "<h4 style=\"margin:16px 0 8px; font-size:15px; color:#0f172a;\">",
    }
    for source, target in replacements.items():
        styled = styled.replace(source, target)

    styled = re.sub(
        r'<a\s+href="([^"]+)"\s*>',
        r'<a href="\1" style="color:#1d4ed8; text-decoration:none;">',
        styled,
    )
    styled = re.sub(
        r"<code\s+class=\"[^\"]+\">",
        "<code style=\"font-family:Consolas,'Courier New',monospace;\">",
        styled,
    )

    return styled


def _render_summary_html(summary: str) -> str:
    normalized_markdown = _normalize_summary_markdown(summary)
    if not normalized_markdown:
        return "<p style=\"margin:0; color:#111827; line-height:1.7;\">요약 내용이 없습니다.</p>"

    safe_markdown = normalized_markdown.replace("<", "&lt;").replace(">", "&gt;")

    try:
        import markdown as markdown_lib  # type: ignore
    except Exception:
        fallback = html.escape(summary)
        return (
            "<pre style=\"margin:0; padding:12px; background:#0f172a; color:#e5e7eb; border-radius:10px; overflow:auto; font-size:12px; line-height:1.6;\">"
            f"{fallback}"
            "</pre>"
        )

    rendered = markdown_lib.markdown(
        safe_markdown,
        extensions=["extra", "sane_lists", "fenced_code", "tables", "nl2br"],
        output_format="html5",
    )
    return _style_rendered_markdown_html(rendered)


def build_email_html_body(
    profile: OnboardingProfile,
    summary: str,
    hr_contact_email: str | None = None,
    slack_invite_link: str | None = None,
) -> str:
    summary_html = _render_summary_html(summary)
    escaped_name = html.escape(profile.name)
    escaped_department = html.escape(profile.department)
    escaped_join_date = html.escape(profile.join_date)
    escaped_email = html.escape(profile.email)
    invite_link_raw = (slack_invite_link or "").strip()
    invite_link_html = ""
    if looks_like_slack_invite_link(invite_link_raw):
        escaped_invite_link = html.escape(invite_link_raw, quote=True)
        invite_link_html = (
            "<tr>"
            "<td style=\"padding:0 28px 20px;\">"
            "<div style=\"padding:16px 18px; border:1px solid #c7d2fe; border-radius:12px; background:#eef2ff;\">"
            "<div style=\"font-size:13px; font-weight:700; color:#3730a3; margin-bottom:8px;\">Slack 워크스페이스 초대 링크</div>"
            "<a href=\""
            + escaped_invite_link
            + "\" style=\"display:inline-block; padding:10px 14px; background:#3730a3; color:#ffffff; text-decoration:none; border-radius:8px; font-size:13px;\">"
            "Slack 참여하기"
            "</a>"
            "<div style=\"margin-top:8px; font-size:12px; color:#475569; word-break:break-all;\">"
            + escaped_invite_link
            + "</div>"
            "</div>"
            "</td>"
            "</tr>"
        )

    hr_contact = (hr_contact_email or "").strip().lower()
    escaped_hr_contact = html.escape(hr_contact) if hr_contact else ""
    hr_contact_html = (
        "문의사항이 있으면 HR/IT 담당자 "
        f"<a href=\"mailto:{escaped_hr_contact}\" style=\"color:#1d4ed8; text-decoration:none;\">{escaped_hr_contact}</a>"
        " 에게 연락 부탁드립니다.<br />"
        if hr_contact
        else "문의사항이 있으면 HR/IT 담당자에게 편하게 연락 부탁드립니다.<br />"
    )

    return f"""<!doctype html>
<html lang=\"ko\">
    <body style=\"margin:0; padding:0; background:#f3f4f6; font-family:Arial,'Noto Sans KR',sans-serif;\">
        <table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"background:#f3f4f6; padding:24px 0;\">
            <tr>
                <td align=\"center\">
                    <table role=\"presentation\" width=\"680\" cellpadding=\"0\" cellspacing=\"0\" style=\"max-width:680px; background:#ffffff; border:1px solid #e5e7eb; border-radius:16px; overflow:hidden;\">
                        <tr>
                            <td style=\"padding:24px 28px; background:#0f172a; color:#ffffff;\">
                                <div style=\"font-size:12px; letter-spacing:0.08em; opacity:0.85;\">ONBOARDING NOTICE</div>
                                <h1 style=\"margin:8px 0 0; font-size:22px; font-weight:700;\">{escaped_name} 님 입사 준비 안내</h1>
                            </td>
                        </tr>
                                    {hr_contact_html}
                        <tr>
                            <td style=\"padding:22px 28px 8px; color:#111827; font-size:15px; line-height:1.75;\">
                                안녕하세요 <strong>{escaped_name}</strong> 님,<br />
                                <strong>{escaped_department}</strong> 입사를 환영합니다. 아래에 입사 준비와 온보딩 정보를 정리해 드립니다.
                            </td>
                        </tr>

                        <tr>
                            <td style=\"padding:0 28px 12px;\">
                                <table role=\"presentation\" width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"border-collapse:collapse; background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; overflow:hidden;\">
                                    <tr>
                                        <td style=\"padding:12px 14px; width:130px; color:#334155; font-size:13px; border-bottom:1px solid #e2e8f0;\">이름</td>
                                        <td style=\"padding:12px 14px; color:#0f172a; font-size:13px; border-bottom:1px solid #e2e8f0;\">{escaped_name}</td>
                                    </tr>
                                    <tr>
                                        <td style=\"padding:12px 14px; color:#334155; font-size:13px; border-bottom:1px solid #e2e8f0;\">부서</td>
                                        <td style=\"padding:12px 14px; color:#0f172a; font-size:13px; border-bottom:1px solid #e2e8f0;\">{escaped_department}</td>
                                    </tr>
                                    <tr>
                                        <td style=\"padding:12px 14px; color:#334155; font-size:13px; border-bottom:1px solid #e2e8f0;\">입사일</td>
                                        <td style=\"padding:12px 14px; color:#0f172a; font-size:13px; border-bottom:1px solid #e2e8f0;\">{escaped_join_date}</td>
                                    </tr>
                                    <tr>
                                        <td style=\"padding:12px 14px; color:#334155; font-size:13px;\">이메일</td>
                                        <td style=\"padding:12px 14px; color:#0f172a; font-size:13px;\">{escaped_email}</td>
                                    </tr>
                                </table>
                            </td>
                        </tr>

                        <tr>
                            <td style=\"padding:8px 28px 24px;\">
                                <div style=\"padding:18px 18px; border:1px solid #dbeafe; border-radius:12px; background:#f8fbff;\">
                                    <div style=\"font-size:13px; font-weight:700; color:#1e3a8a; margin-bottom:10px;\">입사/온보딩 요약</div>
                                    {summary_html}
                                </div>
                            </td>
                        </tr>

                        {invite_link_html}

                        <tr>
                            <td style=\"padding:0 28px 28px; color:#374151; font-size:13px; line-height:1.7;\">
                                문의사항이 있으면 HR/IT 담당자에게 편하게 연락 부탁드립니다.<br />
                                감사합니다.
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
</html>"""


async def send_email_with_gmail(
    recipient_email: str,
    subject: str,
    body: str,
    google_api_key: str,
    html_body: str | None = None,
) -> tuple[bool, str]:
    token = google_api_key.strip()
    if not token:
        return False, "Google API key is not configured."

    if not looks_like_google_oauth_token(token):
        return (
            False,
            "Google key is API key format. Gmail send requires OAuth access token (ya29...).",
        )

    oauth_scopes, token_scope_error = await fetch_google_token_scopes(token)
    if oauth_scopes and not has_any_required_scope(oauth_scopes, GMAIL_SCOPE_HINTS):
        return (
            False,
            (
                "Gmail send blocked: OAuth token missing Gmail scope. "
                f"required scopes: {format_scope_list(GMAIL_SCOPE_HINTS)} | "
                f"granted scopes: {format_scope_list(oauth_scopes)}"
            ),
        )

    message = EmailMessage()
    message["To"] = recipient_email
    message["Subject"] = subject
    message.set_content(body)
    if html_body and html_body.strip():
        message.add_alternative(html_body, subtype="html")

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    try:
        async with httpx.AsyncClient(timeout=20) as http:
            response = await http.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={"Authorization": f"Bearer {token}"},
                json={"raw": raw},
            )
    except Exception as exc:
        return False, f"Gmail send failed: {exc}"

    if response.status_code >= 400:
        return (
            False,
            build_google_http_error_detail(
                prefix="Gmail send failed",
                response=response,
                required_scopes=GMAIL_SCOPE_HINTS,
                granted_scopes=oauth_scopes,
                token_scope_error=token_scope_error,
            ),
        )

    return True, "Email sent via Gmail API"


async def invite_user_to_slack(
    profile: OnboardingProfile,
    settings: Settings,
    slack_api_key: str,
) -> tuple[bool, str]:
    token = slack_api_key.strip()
    if not token:
        return False, "Slack API key is not configured."
    if is_slack_bot_token(token):
        return (
            False,
            (
                "not_allowed_token_type: xoxb bot token cannot invite users by email. "
                "Use Slack admin user token (xoxp- or xoxa-2-) with admin.users:write scope."
            ),
        )
    if not looks_like_slack_token(token):
        return False, "Slack token format is invalid. expected xoxp- or xoxa-2-"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }

    payload: dict[str, Any] = {
        "email": profile.email,
        "real_name": profile.name,
        "resend": True,
    }
    if settings.slack_team_id.strip():
        payload["team_id"] = settings.slack_team_id.strip()

    async with httpx.AsyncClient(timeout=20) as http:
        endpoints = [
            "https://slack.com/api/admin.users.invite",
            "https://slack.com/api/users.admin.invite",
        ]

        errors: list[str] = []
        for endpoint in endpoints:
            try:
                response = await http.post(endpoint, headers=headers, json=payload)
                data = response.json()
            except Exception as exc:
                errors.append(f"{endpoint}: {exc}")
                continue

            if response.status_code >= 400:
                errors.append(f"{endpoint}: HTTP {response.status_code}")
                continue

            if bool(data.get("ok")):
                return True, f"Slack invite requested ({endpoint})"

            err_code = str(data.get("error", "unknown_error"))
            if err_code == "not_allowed_token_type":
                return (
                    False,
                    (
                        "not_allowed_token_type: current token type cannot call workspace invite API. "
                        "Use Slack admin user token (xoxp- or xoxa-2-) with admin.users:write scope."
                    ),
                )
            errors.append(f"{endpoint}: {err_code}")

    return False, "; ".join(errors) if errors else "Slack invite failed"


async def validate_slack_invite_token(
    slack_api_key: str,
    settings: Settings,
) -> tuple[bool, str]:
    token = slack_api_key.strip()
    if not token:
        return False, "Slack API key is not configured."
    if not looks_like_slack_token(token):
        return False, "Slack token format is invalid. expected xoxp- or xoxa-2-"
    if is_slack_bot_token(token):
        return (
            False,
            (
                "not_allowed_token_type: xoxb bot token cannot invite users by email. "
                "Use Slack admin user token (xoxp- or xoxa-2-)"
            ),
        )

    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            response = await http.post(
                "https://slack.com/api/auth.test",
                headers=headers,
                json={},
            )
            payload = response.json()
    except Exception as exc:
        return False, f"Slack auth test failed: {exc}"

    if response.status_code >= 400:
        return False, f"Slack auth test HTTP {response.status_code}"

    if not isinstance(payload, dict):
        return False, "Slack auth test response parse failed"

    if not bool(payload.get("ok")):
        return False, str(payload.get("error", "invalid_auth"))

    workspace_name = str(payload.get("team", "")).strip()
    workspace_id = str(payload.get("team_id", "")).strip()
    team_hint = workspace_name or workspace_id
    if settings.slack_team_id.strip() and workspace_id:
        configured_team = settings.slack_team_id.strip()
        if workspace_id != configured_team:
            return (
                False,
                (
                    "Slack token team mismatch. "
                    f"configured={configured_team}, token_team={workspace_id}"
                ),
            )

    detail = f"token verified ({team_hint})" if team_hint else "token verified"
    return True, detail


async def validate_slack_bot_token(
    slack_api_key: str,
    settings: Settings,
) -> tuple[bool, str]:
    return await validate_slack_invite_token(slack_api_key, settings)


def build_workflow_report(
    profile: OnboardingProfile,
    files: list[dict[str, Any]],
    summary: str,
    email_sent: bool,
    email_detail: str,
    slack_invited: bool,
    slack_detail: str,
    drive_error: str | None,
) -> str:
    file_lines = render_file_list(files)
    drive_state = "검색 성공" if files else "검색 결과 없음"
    if drive_error:
        drive_state = f"검색 실패 ({drive_error})"

    slack_token_type_hint = ""
    if "not_allowed_token_type" in slack_detail:
        slack_token_type_hint = (
            "- 안내: xoxb 봇 토큰으로는 워크스페이스 이메일 초대 API를 사용할 수 없습니다. "
            "Tools의 Slack API Key에 관리자 사용자 토큰(xoxp- 또는 xoxa-2-)을 설정해 주세요.\n"
        )

    slack_invite_link_hint = ""
    if "Slack invite link format is invalid" in slack_detail:
        slack_invite_link_hint = (
            "- 안내: Slack 초대 링크 형식이 올바르지 않습니다. "
            "Tools의 Slack Invite Link에 shared_invite URL을 입력해 주세요.\n"
        )

    return (
        "# 온보딩 자동화 결과\n\n"
        "## 대상자 정보\n"
        f"- 이름: {profile.name}\n"
        f"- 부서: {profile.department}\n"
        f"- 입사일: {profile.join_date}\n"
        f"- 이메일: {profile.email}\n\n"
        "## Google Drive 탐색 결과\n"
        f"- 상태: {drive_state}\n"
        f"{file_lines}\n\n"
        "## 입사/온보딩 파일 요약\n"
        f"{summary}\n\n"
        "## 액션 실행 결과\n"
        f"- 이메일 전송: {'성공' if email_sent else '실패'} ({email_detail})\n"
        f"- 슬랙 초대: {'성공' if slack_invited else '실패'} ({slack_detail})\n"
        f"{slack_token_type_hint}\n"
        f"{slack_invite_link_hint}\n"
        "참고: Gmail 발송은 OAuth token + gmail.send scope, Drive 탐색은 drive.readonly 또는 drive.metadata.readonly scope가 필요합니다."
    )


async def run_onboarding_workflow(
    profile: OnboardingProfile,
    settings: Settings,
    client: AsyncOpenAI,
    secrets: IntegrationSecrets,
    on_progress: Callable[[dict[str, object]], None] | None = None,
) -> OnboardingWorkflowResult:
    def emit(phase: str, detail: str) -> None:
        if on_progress is None:
            return
        on_progress(
            {
                "phase": phase,
                "detail": detail,
                "updated_at": utc_now_iso(),
            }
        )

    emit("drive-search", "Google Drive 온보딩 파일을 검색하는 중입니다.")
    files, drive_error = await search_google_drive_files(profile, settings, secrets)

    configured_slack_invite_link = (secrets.slack_invite_link or "").strip()
    valid_slack_invite_link = (
        configured_slack_invite_link
        if looks_like_slack_invite_link(configured_slack_invite_link)
        else ""
    )
    invalid_slack_invite_link = bool(
        configured_slack_invite_link and not valid_slack_invite_link
    )

    hr_contact_email, _ = await fetch_google_authenticated_email(secrets.google_api_key)

    emit("summary", "검색된 파일 기반으로 온보딩 요약을 생성하는 중입니다.")
    try:
        summary = await generate_onboarding_summary(
            client=client,
            settings=settings,
            profile=profile,
            files=files,
            drive_error=drive_error,
            hr_contact_email=hr_contact_email,
        )
    except Exception as exc:
        summary = (
            "요약 생성 중 오류가 발생했습니다.\n"
            f"- 오류: {exc}\n"
            f"- 검색 파일 수: {len(files)}"
        )

    emit("email", "신규 입사자에게 요약 이메일을 전송하는 중입니다.")
    email_subject = build_email_subject(profile)
    email_body = build_email_body(
        profile,
        summary,
        hr_contact_email=hr_contact_email,
        slack_invite_link=valid_slack_invite_link or None,
    )
    email_html_body = build_email_html_body(
        profile,
        summary,
        hr_contact_email=hr_contact_email,
        slack_invite_link=valid_slack_invite_link or None,
    )
    try:
        email_sent, email_detail = await send_email_with_gmail(
            recipient_email=profile.email,
            subject=email_subject,
            body=email_body,
            google_api_key=secrets.google_api_key,
            html_body=email_html_body,
        )
    except Exception as exc:
        email_sent, email_detail = False, f"Email step failed: {exc}"

    if valid_slack_invite_link:
        emit("slack", "슬랙 공유 초대 링크를 온보딩 이메일에 포함했습니다.")
        slack_invited = True
        slack_detail = "shared invite link included in onboarding email"
    elif invalid_slack_invite_link:
        emit("slack", "슬랙 공유 초대 링크 형식을 확인해 주세요.")
        slack_invited = False
        slack_detail = (
            "Slack invite link format is invalid. "
            "expected: https://join.slack.com/t/<workspace>/shared_invite/<token>"
        )
    else:
        emit("slack", "슬랙 워크스페이스 초대 요청을 전송하는 중입니다.")
        try:
            slack_invited, slack_detail = await invite_user_to_slack(
                profile=profile,
                settings=settings,
                slack_api_key=secrets.slack_api_key,
            )
        except Exception as exc:
            slack_invited, slack_detail = False, f"Slack step failed: {exc}"

    report = build_workflow_report(
        profile=profile,
        files=files,
        summary=summary,
        email_sent=email_sent,
        email_detail=email_detail,
        slack_invited=slack_invited,
        slack_detail=slack_detail,
        drive_error=drive_error,
    )

    emit("completed", "온보딩 자동화 작업이 완료되었습니다.")

    return OnboardingWorkflowResult(
        report=report,
        email_sent=email_sent,
        email_detail=email_detail,
        slack_invited=slack_invited,
        slack_detail=slack_detail,
        matched_files=files,
    )
