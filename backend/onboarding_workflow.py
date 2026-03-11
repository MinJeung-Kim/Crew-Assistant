from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
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
    if looks_like_google_oauth_token(google_key):
        headers["Authorization"] = f"Bearer {google_key}"
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
        return [], f"Google Drive request failed: HTTP {response.status_code}"

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
) -> str:
    file_list = render_file_list(files)
    error_context = f"\nDrive Error: {drive_error}" if drive_error else ""

    completion = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an HR onboarding coordinator. "
                    "Write concise Korean onboarding email summary using the provided employee profile and file list. "
                    "Return sections: 1) 입사 서류 요약 2) 온보딩 파일 요약 3) 첫 주 체크리스트."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Employee: {profile.name}\n"
                    f"Department: {profile.department}\n"
                    f"Join Date: {profile.join_date}\n"
                    f"Email: {profile.email}\n\n"
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
        "- 계정 발급, 보안교육, 팀 온보딩 미팅을 순서대로 진행합니다."
    )


def build_email_subject(profile: OnboardingProfile) -> str:
    return f"[온보딩 안내] {profile.name} 님 입사 준비 자료 안내"


def build_email_body(profile: OnboardingProfile, summary: str) -> str:
    return (
        f"안녕하세요 {profile.name} 님,\n\n"
        f"{profile.department} 입사를 환영합니다. (입사일: {profile.join_date})\n"
        "아래에 입사 서류와 온보딩 자료 요약을 전달드립니다.\n\n"
        f"{summary}\n\n"
        "문의사항이 있으면 HR/IT 담당자에게 편하게 연락 부탁드립니다.\n"
        "감사합니다."
    )


async def send_email_with_gmail(
    recipient_email: str,
    subject: str,
    body: str,
    google_api_key: str,
) -> tuple[bool, str]:
    token = google_api_key.strip()
    if not token:
        return False, "Google API key is not configured."

    if not looks_like_google_oauth_token(token):
        return (
            False,
            "Google key is API key format. Gmail send requires OAuth access token (ya29...).",
        )

    message = EmailMessage()
    message["To"] = recipient_email
    message["Subject"] = subject
    message.set_content(body)

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
        return False, f"Gmail send failed: HTTP {response.status_code}"

    return True, "Email sent via Gmail API"


async def invite_user_to_slack(
    profile: OnboardingProfile,
    settings: Settings,
    slack_api_key: str,
) -> tuple[bool, str]:
    token = slack_api_key.strip()
    if not token:
        return False, "Slack API key is not configured."

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
            errors.append(f"{endpoint}: {err_code}")

    return False, "; ".join(errors) if errors else "Slack invite failed"


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
        f"- 슬랙 초대: {'성공' if slack_invited else '실패'} ({slack_detail})\n\n"
        "참고: Gmail 발송은 Google OAuth access token(ya29...)이 필요합니다."
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

    emit("summary", "검색된 파일 기반으로 온보딩 요약을 생성하는 중입니다.")
    try:
        summary = await generate_onboarding_summary(
            client=client,
            settings=settings,
            profile=profile,
            files=files,
            drive_error=drive_error,
        )
    except Exception as exc:
        summary = (
            "요약 생성 중 오류가 발생했습니다.\n"
            f"- 오류: {exc}\n"
            f"- 검색 파일 수: {len(files)}"
        )

    emit("email", "신규 입사자에게 요약 이메일을 전송하는 중입니다.")
    email_subject = build_email_subject(profile)
    email_body = build_email_body(profile, summary)
    try:
        email_sent, email_detail = await send_email_with_gmail(
            recipient_email=profile.email,
            subject=email_subject,
            body=email_body,
            google_api_key=secrets.google_api_key,
        )
    except Exception as exc:
        email_sent, email_detail = False, f"Email step failed: {exc}"

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
