from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import asyncio
from dataclasses import dataclass
import json
from pathlib import Path
import secrets
import time
from typing import Literal
from urllib.parse import urlencode, urlparse

from fastapi import FastAPI, Depends, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel, Field, field_validator

from config import Settings, get_settings
from crew import should_route_to_crewai
from knowledge_base import CompanyKnowledgeBase, extract_text_from_upload
from onboarding_workflow import (
    DRIVE_SCOPE_HINTS,
    GMAIL_SCOPE_HINTS,
    IntegrationSecrets,
    OnboardingProfile,
    extract_slack_invite_link,
    extract_slack_token,
    fetch_google_token_scopes,
    has_any_required_scope,
    looks_like_google_oauth_token,
    mask_secret,
    parse_onboarding_profile,
    run_onboarding_workflow,
    utc_now_iso,
    validate_slack_invite_token,
)
from services.chat_service import (
    inject_company_context,
    latest_user_prompt,
    load_company_context,
    run_crewai_report,
    run_default_llm_chat,
    run_translation,
)
from services.google_oauth import (
    GOOGLE_OAUTH_REQUESTED_SCOPES,
    GOOGLE_OAUTH_STATE_TTL_SECONDS,
    GoogleOAuthClientConfig,
    build_google_oauth_popup_html,
    extract_oauth_token_error_message,
    issue_google_token_with_installed_flow,
    parse_expires_in_seconds,
    parse_google_oauth_client_config,
    parse_google_scope_values,
    persist_google_credentials_from_token_payload,
    prune_google_oauth_states,
    resolve_google_oauth_token_file,
    should_sync_google_oauth_store,
    sync_google_access_token_from_token_file,
)
from services.streaming import done_sse_payload, format_sse_payload, iter_text_chunks


# ─── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.llm_client = AsyncOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
    )
    app.state.knowledge_base = CompanyKnowledgeBase(settings.rag_storage_path)
    app.state.integration_secrets = IntegrationSecrets(
        google_api_key=settings.google_api_key.strip(),
        slack_api_key=settings.slack_api_key.strip(),
        slack_invite_link=settings.slack_invite_link.strip(),
        updated_at=(
            utc_now_iso()
            if (
                settings.google_api_key.strip()
                or settings.slack_api_key.strip()
                or settings.slack_invite_link.strip()
            )
            else None
        ),
    )
    app.state.google_oauth_client = None
    app.state.google_oauth_states = {}
    app.state.google_oauth_token_file = resolve_google_oauth_token_file(settings)
    app.state.pending_onboarding_by_session = {}

    startup_sync_result = await sync_google_access_token_from_store_if_needed()
    if startup_sync_result.get("synced"):
        print(
            "✅ Google OAuth token store loaded "
            f"token={startup_sync_result.get('access_token_masked', 'hidden')}"
        )
    elif startup_sync_result.get("error"):
        print(f"⚠️ Google OAuth token store sync skipped: {startup_sync_result['error']}")

    print(f"✅ LLM client ready  model={settings.llm_model}  url={settings.llm_base_url}")
    print(f"✅ Knowledge base ready path={settings.rag_storage_path}")
    print("✅ Integration secret store ready")
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


ONBOARDING_PENDING_TTL_SECONDS = 10 * 60
ONBOARDING_CANCEL_COMMANDS = {
    "cancel",
    "onboarding cancel",
    "취소",
    "온보딩 취소",
}


@dataclass
class PendingOnboardingSession:
    profile: OnboardingProfile
    created_at_epoch: float
    expires_at_epoch: float


def pending_onboarding_store() -> dict[str, PendingOnboardingSession]:
    store = getattr(app.state, "pending_onboarding_by_session", None)
    if isinstance(store, dict):
        return store

    app.state.pending_onboarding_by_session = {}
    return app.state.pending_onboarding_by_session


def prune_pending_onboarding_sessions(*, now_epoch: float | None = None) -> None:
    store = pending_onboarding_store()
    now_value = time.time() if now_epoch is None else now_epoch
    expired_session_ids = [
        session_id
        for session_id, state in store.items()
        if state.expires_at_epoch <= now_value
    ]
    for session_id in expired_session_ids:
        store.pop(session_id, None)


def set_pending_onboarding_session(
    session_id: str,
    profile: OnboardingProfile,
) -> PendingOnboardingSession:
    prune_pending_onboarding_sessions()
    now_epoch = time.time()
    state = PendingOnboardingSession(
        profile=profile,
        created_at_epoch=now_epoch,
        expires_at_epoch=now_epoch + ONBOARDING_PENDING_TTL_SECONDS,
    )
    pending_onboarding_store()[session_id] = state
    return state


def get_pending_onboarding_session(session_id: str) -> PendingOnboardingSession | None:
    prune_pending_onboarding_sessions()
    state = pending_onboarding_store().get(session_id)
    if state is None:
        return None

    if state.expires_at_epoch <= time.time():
        pending_onboarding_store().pop(session_id, None)
        return None

    return state


def clear_pending_onboarding_session(session_id: str) -> None:
    pending_onboarding_store().pop(session_id, None)


def is_onboarding_cancel_command(prompt: str) -> bool:
    return prompt.strip().lower() in ONBOARDING_CANCEL_COMMANDS


def build_onboarding_token_request_message(profile: OnboardingProfile) -> str:
    wait_minutes = ONBOARDING_PENDING_TTL_SECONDS // 60
    return (
        "온보딩 대상자 정보를 확인했습니다.\\n"
        f"- 이름: {profile.name}\\n"
        f"- 부서: {profile.department}\\n"
        f"- 입사일: {profile.join_date}\\n"
        f"- 이메일: {profile.email}\\n\\n"
        "Tools 화면에 Slack Invite Link를 저장하면 다음부터 채팅 입력 없이 자동으로 이메일에 포함됩니다.\\n"
        "현재 세션에는 Slack 초대 링크가 없어 입력이 필요합니다.\\n"
        "shared_invite URL(https://join.slack.com/t/.../shared_invite/...)을 입력해 주세요.\\n"
        "(필요하면 관리자 토큰 xoxp-/xoxa-2-도 사용할 수 있습니다.)\\n"
        f"{wait_minutes}분 안에 입력하지 않으면 요청이 만료됩니다. 취소하려면 '취소'를 입력해 주세요."
    )


def build_onboarding_token_missing_message() -> str:
    return (
        "현재 온보딩 요청은 Slack 초대 정보 입력을 기다리고 있습니다.\\n"
        "shared_invite URL(권장) 또는 관리자 토큰(xoxp-/xoxa-2-)을 입력해 주세요.\\n"
        "취소하려면 '취소'를 입력해 주세요."
    )


def build_onboarding_token_invalid_message(detail: str) -> str:
    safe_detail = detail.strip() or "invalid token"
    return (
        "Slack 초대 정보 검증에 실패했습니다.\\n"
        f"- 상세: {safe_detail}\\n"
        "shared_invite URL 또는 관리자 토큰을 다시 입력하거나 '취소'를 입력해 주세요."
    )


def build_onboarding_cancel_message() -> str:
    return (
        "온보딩 초대 정보 입력 대기를 취소했습니다.\\n"
        "다시 시작하려면 [이름] [부서] [입사일] [이메일] 형식으로 입력해 주세요."
    )


async def run_onboarding_with_runtime_slack_token(
    *,
    profile: OnboardingProfile,
    slack_token: str | None = None,
    slack_invite_link: str | None = None,
    settings: Settings,
    client: AsyncOpenAI,
    on_progress=None,
):
    await sync_google_access_token_from_store_if_needed()
    stored_secrets: IntegrationSecrets = app.state.integration_secrets
    workflow_secrets = IntegrationSecrets(
        google_api_key=stored_secrets.google_api_key,
        slack_api_key=(
            slack_token
            if slack_token is not None
            else stored_secrets.slack_api_key
        ),
        slack_invite_link=(
            slack_invite_link
            if slack_invite_link is not None
            else stored_secrets.slack_invite_link
        ),
        updated_at=stored_secrets.updated_at,
    )
    return await run_onboarding_workflow(
        profile=profile,
        settings=settings,
        client=client,
        secrets=workflow_secrets,
        on_progress=on_progress,
    )


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


class EnvSecretsUpdateRequest(BaseModel):
    google_api_key: str | None = Field(default=None, max_length=4096)
    slack_api_key: str | None = Field(default=None, max_length=4096)
    slack_invite_link: str | None = Field(default=None, max_length=4096)

    @field_validator("google_api_key", "slack_api_key", "slack_invite_link")
    @classmethod
    def normalize_secret(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if any(ord(ch) < 32 for ch in normalized):
            raise ValueError("secret contains control characters")
        return normalized


class EnvSecretsStatusResponse(BaseModel):
    has_google_api_key: bool
    has_slack_api_key: bool
    has_slack_invite_link: bool
    google_api_key_masked: str | None = None
    slack_api_key_masked: str | None = None
    slack_invite_link_masked: str | None = None
    updated_at: str | None = None


class GoogleScopeStatusResponse(BaseModel):
    token_configured: bool
    token_type: str | None = None
    granted_scopes: list[str] = []
    drive_scope_ready: bool = False
    gmail_scope_ready: bool = False
    drive_scope_hints: list[str] = []
    gmail_scope_hints: list[str] = []
    tokeninfo_error: str | None = None


class GoogleOAuthClientStatusResponse(BaseModel):
    configured: bool
    client_type: str | None = None
    project_id: str | None = None
    client_id_masked: str | None = None
    redirect_uri: str | None = None


class GoogleOAuthStartResponse(BaseModel):
    auth_url: str
    expires_in_seconds: int


class GoogleOAuthInstalledIssueResponse(BaseModel):
    message: str
    access_token_masked: str | None = None
    token_type: str | None = None
    expires_in_seconds: int | None = None
    granted_scopes: list[str] = []


def build_env_secrets_status(secrets: IntegrationSecrets) -> EnvSecretsStatusResponse:
    google_key = secrets.google_api_key.strip()
    slack_key = secrets.slack_api_key.strip()
    slack_invite_link = (secrets.slack_invite_link or "").strip()
    return EnvSecretsStatusResponse(
        has_google_api_key=bool(google_key),
        has_slack_api_key=bool(slack_key),
        has_slack_invite_link=bool(slack_invite_link),
        google_api_key_masked=mask_secret(google_key),
        slack_api_key_masked=mask_secret(slack_key),
        slack_invite_link_masked=mask_secret(slack_invite_link),
        updated_at=secrets.updated_at,
    )


def build_google_oauth_client_status(
    client: GoogleOAuthClientConfig | None,
) -> GoogleOAuthClientStatusResponse:
    if client is None:
        return GoogleOAuthClientStatusResponse(configured=False)

    return GoogleOAuthClientStatusResponse(
        configured=True,
        client_type=client.client_type,
        project_id=client.project_id,
        client_id_masked=mask_secret(client.client_id),
        redirect_uri=client.redirect_uri,
    )
async def sync_google_access_token_from_store_if_needed(
    *,
    force: bool = False,
) -> dict[str, object]:
    secrets_store: IntegrationSecrets = app.state.integration_secrets
    if not force and not should_sync_google_oauth_store(secrets_store):
        return {"synced": False, "reason": "manual-api-key-in-use"}

    token_file: Path = app.state.google_oauth_token_file
    try:
        return await asyncio.to_thread(
            sync_google_access_token_from_token_file,
            token_file,
            secrets_store,
        )
    except RuntimeError as exc:
        return {"synced": False, "error": str(exc)}


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


@app.get("/integrations/env", response_model=EnvSecretsStatusResponse)
async def integrations_env_status() -> EnvSecretsStatusResponse:
    await sync_google_access_token_from_store_if_needed()
    secrets: IntegrationSecrets = app.state.integration_secrets
    return build_env_secrets_status(secrets)


@app.post("/integrations/env", response_model=EnvSecretsStatusResponse)
async def integrations_env_update(req: EnvSecretsUpdateRequest) -> EnvSecretsStatusResponse:
    secrets: IntegrationSecrets = app.state.integration_secrets
    changed = False

    if req.google_api_key is not None:
        secrets.google_api_key = req.google_api_key
        changed = True

    if req.slack_api_key is not None:
        secrets.slack_api_key = req.slack_api_key
        changed = True

    if req.slack_invite_link is not None:
        secrets.slack_invite_link = req.slack_invite_link
        changed = True

    if changed:
        secrets.updated_at = utc_now_iso()

    return build_env_secrets_status(secrets)


@app.get(
    "/integrations/google/oauth-client/status",
    response_model=GoogleOAuthClientStatusResponse,
)
async def integrations_google_oauth_client_status() -> GoogleOAuthClientStatusResponse:
    client: GoogleOAuthClientConfig | None = app.state.google_oauth_client
    return build_google_oauth_client_status(client)


@app.delete(
    "/integrations/google/oauth-client",
    response_model=GoogleOAuthClientStatusResponse,
)
async def integrations_google_oauth_client_clear() -> GoogleOAuthClientStatusResponse:
    app.state.google_oauth_client = None
    app.state.google_oauth_states = {}
    return build_google_oauth_client_status(None)


@app.post(
    "/integrations/google/oauth-client",
    response_model=GoogleOAuthClientStatusResponse,
)
async def integrations_google_oauth_client_upload(
    request: Request,
    file: UploadFile = File(...),
) -> GoogleOAuthClientStatusResponse:
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="OAuth client JSON 파일명이 필요합니다.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="OAuth client JSON 파일이 비어 있습니다.")
    if len(content) > 1_000_000:
        raise HTTPException(status_code=413, detail="OAuth client JSON 파일이 너무 큽니다.")

    try:
        payload = json.loads(content.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"JSON 파싱 실패: {exc}") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="OAuth client JSON은 객체 형태여야 합니다.")

    callback_candidates: list[str] = []

    def append_callback_candidate(
        *,
        scheme: str,
        host: str | None,
        port: int | None,
    ) -> None:
        host_value = (host or "").strip()
        if not host_value:
            return

        host_candidates = [host_value]
        if host_value in {"localhost", "127.0.0.1", "::1"}:
            host_candidates = ["localhost", "127.0.0.1"]

        for candidate_host in host_candidates:
            if port is not None:
                candidate = (
                    f"{scheme}://{candidate_host}:{port}"
                    "/integrations/google/oauth/callback"
                )
            else:
                candidate = (
                    f"{scheme}://{candidate_host}"
                    "/integrations/google/oauth/callback"
                )

            normalized = candidate.rstrip("/")
            if normalized and normalized not in callback_candidates:
                callback_candidates.append(normalized)

    frontend_origin_raw = request.headers.get("x-frontend-origin", "").strip()
    backend_base_raw = str(request.base_url).rstrip("/")
    backend_base_parts = urlparse(backend_base_raw)
    backend_scheme = backend_base_parts.scheme or "http"
    backend_port = backend_base_parts.port

    if frontend_origin_raw:
        try:
            frontend_parts = urlparse(frontend_origin_raw)
            frontend_host = (frontend_parts.hostname or "").strip()
            append_callback_candidate(
                scheme=backend_scheme,
                host=frontend_host,
                port=backend_port,
            )
        except Exception:
            pass

    append_callback_candidate(
        scheme=backend_scheme,
        host=backend_base_parts.hostname,
        port=backend_port,
    )
    normalized_backend_callback = (
        f"{backend_base_raw}/integrations/google/oauth/callback"
    ).rstrip("/")
    if normalized_backend_callback and normalized_backend_callback not in callback_candidates:
        callback_candidates.append(normalized_backend_callback)

    try:
        client = parse_google_oauth_client_config(
            payload,
            callback_uris=callback_candidates,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    app.state.google_oauth_client = client
    return build_google_oauth_client_status(client)


@app.get(
    "/integrations/google/oauth/start",
    response_model=GoogleOAuthStartResponse,
)
async def integrations_google_oauth_start() -> GoogleOAuthStartResponse:
    client: GoogleOAuthClientConfig | None = app.state.google_oauth_client
    if client is None:
        raise HTTPException(
            status_code=400,
            detail="먼저 Google OAuth client JSON을 업로드해 주세요.",
        )

    if client.client_type == "installed":
        raise HTTPException(
            status_code=400,
            detail=(
                "Installed/Desktop OAuth client는 /integrations/google/oauth/installed/issue "
                "엔드포인트로 key 발급을 진행해 주세요."
            ),
        )

    states: dict[str, float] = app.state.google_oauth_states
    prune_google_oauth_states(states)

    state = secrets.token_urlsafe(24)
    states[state] = time.time() + GOOGLE_OAUTH_STATE_TTL_SECONDS

    query = urlencode(
        {
            "client_id": client.client_id,
            "redirect_uri": client.redirect_uri,
            "response_type": "code",
            "scope": " ".join(GOOGLE_OAUTH_REQUESTED_SCOPES),
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
        }
    )
    auth_url = f"{client.auth_uri}?{query}"

    return GoogleOAuthStartResponse(
        auth_url=auth_url,
        expires_in_seconds=GOOGLE_OAUTH_STATE_TTL_SECONDS,
    )


@app.post(
    "/integrations/google/oauth/installed/issue",
    response_model=GoogleOAuthInstalledIssueResponse,
)
async def integrations_google_oauth_issue_installed(
    settings: Settings = Depends(get_settings),
) -> GoogleOAuthInstalledIssueResponse:
    client: GoogleOAuthClientConfig | None = app.state.google_oauth_client
    if client is None:
        raise HTTPException(
            status_code=400,
            detail="먼저 Google OAuth client JSON을 업로드해 주세요.",
        )

    if client.client_type != "installed":
        raise HTTPException(
            status_code=400,
            detail="현재 등록된 OAuth client는 installed 타입이 아닙니다.",
        )

    token_file: Path = app.state.google_oauth_token_file
    try:
        issued = await asyncio.to_thread(
            issue_google_token_with_installed_flow,
            client=client,
            token_file=token_file,
            port=settings.google_oauth_installed_port,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Installed OAuth 발급 실패: {exc}") from exc

    access_token = str(issued.get("access_token", "") or "").strip()
    if not access_token:
        raise HTTPException(status_code=502, detail="Installed OAuth 발급 결과에 access_token이 없습니다.")

    integration_secrets: IntegrationSecrets = app.state.integration_secrets
    integration_secrets.google_api_key = access_token
    integration_secrets.updated_at = utc_now_iso()

    return GoogleOAuthInstalledIssueResponse(
        message="Installed OAuth 발급이 완료되었습니다. token.json 저장 및 자동 갱신이 활성화되었습니다.",
        access_token_masked=str(issued.get("access_token_masked") or "") or None,
        token_type=str(issued.get("token_type") or "") or None,
        expires_in_seconds=(
            int(issued["expires_in_seconds"])
            if isinstance(issued.get("expires_in_seconds"), int)
            else None
        ),
        granted_scopes=(
            [scope for scope in issued.get("granted_scopes", []) if isinstance(scope, str)]
            if isinstance(issued.get("granted_scopes"), list)
            else []
        ),
    )


@app.get("/integrations/google/oauth/callback", response_class=HTMLResponse)
async def integrations_google_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    if error:
        return build_google_oauth_popup_html(False, f"Google OAuth 인증 오류: {error}")

    if not code or not state:
        return build_google_oauth_popup_html(False, "OAuth callback 파라미터(code/state)가 누락되었습니다.")

    client: GoogleOAuthClientConfig | None = app.state.google_oauth_client
    if client is None:
        return build_google_oauth_popup_html(False, "OAuth client JSON이 아직 등록되지 않았습니다.")

    states: dict[str, float] = app.state.google_oauth_states
    prune_google_oauth_states(states)
    state_expiration = states.pop(state, None)
    if state_expiration is None or state_expiration <= time.time():
        return build_google_oauth_popup_html(False, "OAuth state가 유효하지 않거나 만료되었습니다. 다시 시도해 주세요.")

    try:
        async with httpx.AsyncClient(timeout=20) as http_client:
            token_response = await http_client.post(
                client.token_uri,
                data={
                    "code": code,
                    "client_id": client.client_id,
                    "client_secret": client.client_secret,
                    "redirect_uri": client.redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
    except Exception as exc:
        return build_google_oauth_popup_html(False, f"토큰 교환 요청 실패: {exc}")

    if token_response.status_code >= 400:
        detail = extract_oauth_token_error_message(token_response)
        message = f"토큰 교환 실패 (HTTP {token_response.status_code})"
        if detail:
            message = f"{message}: {detail}"
        return build_google_oauth_popup_html(False, message)

    try:
        token_payload = token_response.json()
    except Exception:
        return build_google_oauth_popup_html(False, "토큰 교환 응답 파싱에 실패했습니다.")

    if not isinstance(token_payload, dict):
        return build_google_oauth_popup_html(False, "토큰 교환 응답 형식이 올바르지 않습니다.")

    access_token = str(token_payload.get("access_token", "")).strip()
    if not access_token:
        return build_google_oauth_popup_html(False, "발급된 access_token이 비어 있습니다.")

    token_type = str(token_payload.get("token_type", "")).strip() or None

    expires_in_seconds = parse_expires_in_seconds(token_payload.get("expires_in"))
    granted_scopes = parse_google_scope_values(token_payload.get("scope"))

    integration_secrets: IntegrationSecrets = app.state.integration_secrets
    integration_secrets.google_api_key = access_token
    integration_secrets.updated_at = utc_now_iso()

    token_file: Path = app.state.google_oauth_token_file
    persist_warning = persist_google_credentials_from_token_payload(
        token_file=token_file,
        client=client,
        token_payload=token_payload,
        granted_scopes=granted_scopes,
        expires_in_seconds=expires_in_seconds,
    )

    success_message = "Google OAuth Access Token이 저장되었습니다."
    if persist_warning:
        success_message = f"{success_message} (참고: {persist_warning})"

    return build_google_oauth_popup_html(
        True,
        success_message,
        payload_extra={
            "flow_step": "token-saved",
            "token_type": token_type,
            "expires_in_seconds": expires_in_seconds,
            "granted_scopes": granted_scopes,
            "access_token_masked": mask_secret(access_token),
        },
    )


@app.get("/integrations/google/scope-status", response_model=GoogleScopeStatusResponse)
async def integrations_google_scope_status() -> GoogleScopeStatusResponse:
    sync_result = await sync_google_access_token_from_store_if_needed()

    secrets: IntegrationSecrets = app.state.integration_secrets
    token = secrets.google_api_key.strip()
    sync_error = str(sync_result.get("error") or "").strip() or None

    if not token:
        return GoogleScopeStatusResponse(
            token_configured=False,
            token_type=None,
            drive_scope_hints=list(DRIVE_SCOPE_HINTS),
            gmail_scope_hints=list(GMAIL_SCOPE_HINTS),
            tokeninfo_error=sync_error,
        )

    if not looks_like_google_oauth_token(token):
        return GoogleScopeStatusResponse(
            token_configured=True,
            token_type="api_key",
            granted_scopes=[],
            drive_scope_ready=False,
            gmail_scope_ready=False,
            drive_scope_hints=list(DRIVE_SCOPE_HINTS),
            gmail_scope_hints=list(GMAIL_SCOPE_HINTS),
            tokeninfo_error=(
                "Google key is API key format. OAuth token required for scope-based checks."
                if not sync_error
                else f"Google key is API key format. OAuth token required for scope-based checks. | {sync_error}"
            ),
        )

    scopes, tokeninfo_error = await fetch_google_token_scopes(token)
    drive_scope_ready = has_any_required_scope(scopes, DRIVE_SCOPE_HINTS)
    gmail_scope_ready = has_any_required_scope(scopes, GMAIL_SCOPE_HINTS)

    return GoogleScopeStatusResponse(
        token_configured=True,
        token_type="oauth_token",
        granted_scopes=sorted(scopes),
        drive_scope_ready=drive_scope_ready,
        gmail_scope_ready=gmail_scope_ready,
        drive_scope_hints=list(DRIVE_SCOPE_HINTS),
        gmail_scope_hints=list(GMAIL_SCOPE_HINTS),
        tokeninfo_error=(
            tokeninfo_error
            if not sync_error
            else (f"{tokeninfo_error} | {sync_error}" if tokeninfo_error else sync_error)
        ),
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
    await sync_google_access_token_from_store_if_needed()
    integration_secrets: IntegrationSecrets = app.state.integration_secrets
    user_prompt = latest_user_prompt(req.messages)
    knowledge_base: CompanyKnowledgeBase = app.state.knowledge_base
    company_context, knowledge_sources = await load_company_context(
        user_prompt,
        settings,
        knowledge_base=knowledge_base,
        client=client,
        google_api_key=integration_secrets.google_api_key,
    )

    onboarding_profile = parse_onboarding_profile(user_prompt)
    if onboarding_profile is not None:
        configured_slack_invite_link = integration_secrets.slack_invite_link.strip()
        configured_slack_token = integration_secrets.slack_api_key.strip()
        if configured_slack_invite_link or configured_slack_token:
            clear_pending_onboarding_session(req.session_id)
            try:
                result = await run_onboarding_with_runtime_slack_token(
                    profile=onboarding_profile,
                    settings=settings,
                    client=client,
                )
                return ChatResponse(
                    message=result.report,
                    session_id=req.session_id,
                    source="onboarding",
                    knowledge_sources=knowledge_sources or None,
                )
            except Exception as exc:
                return ChatResponse(
                    message=f"온보딩 자동화 실행 실패: {exc}",
                    session_id=req.session_id,
                    source="onboarding",
                    knowledge_sources=knowledge_sources or None,
                )

        set_pending_onboarding_session(req.session_id, onboarding_profile)
        return ChatResponse(
            message=build_onboarding_token_request_message(onboarding_profile),
            session_id=req.session_id,
            source="onboarding",
            knowledge_sources=knowledge_sources or None,
        )

    pending_onboarding = get_pending_onboarding_session(req.session_id)
    if pending_onboarding is not None:
        if is_onboarding_cancel_command(user_prompt):
            clear_pending_onboarding_session(req.session_id)
            return ChatResponse(
                message=build_onboarding_cancel_message(),
                session_id=req.session_id,
                source="onboarding",
                knowledge_sources=knowledge_sources or None,
            )

        submitted_invite_link = extract_slack_invite_link(user_prompt)
        submitted_token = extract_slack_token(user_prompt)
        if not submitted_invite_link and not submitted_token:
            return ChatResponse(
                message=build_onboarding_token_missing_message(),
                session_id=req.session_id,
                source="onboarding",
                knowledge_sources=knowledge_sources or None,
            )

        if submitted_token:
            token_valid, token_detail = await validate_slack_invite_token(
                submitted_token,
                settings,
            )
            if not token_valid:
                return ChatResponse(
                    message=build_onboarding_token_invalid_message(token_detail),
                    session_id=req.session_id,
                    source="onboarding",
                    knowledge_sources=knowledge_sources or None,
                )

        try:
            result = await run_onboarding_with_runtime_slack_token(
                profile=pending_onboarding.profile,
                slack_token=submitted_token if submitted_token else None,
                slack_invite_link=(
                    submitted_invite_link
                    if submitted_invite_link is not None
                    else None
                ),
                settings=settings,
                client=client,
            )
            clear_pending_onboarding_session(req.session_id)
            return ChatResponse(
                message=result.report,
                session_id=req.session_id,
                source="onboarding",
                knowledge_sources=knowledge_sources or None,
            )
        except Exception as exc:
            return ChatResponse(
                message=(
                    f"온보딩 자동화 실행 실패: {exc}\\n"
                    "초대 링크(또는 관리자 토큰)를 다시 입력하거나 '취소'를 입력해 주세요."
                ),
                session_id=req.session_id,
                source="onboarding",
                knowledge_sources=knowledge_sources or None,
            )

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
    await sync_google_access_token_from_store_if_needed()
    integration_secrets: IntegrationSecrets = app.state.integration_secrets
    user_prompt = latest_user_prompt(req.messages)
    knowledge_base: CompanyKnowledgeBase = app.state.knowledge_base
    company_context, knowledge_sources = await load_company_context(
        user_prompt,
        settings,
        knowledge_base=knowledge_base,
        client=client,
        google_api_key=integration_secrets.google_api_key,
    )

    async def token_generator() -> AsyncIterator[str]:
        onboarding_profile = parse_onboarding_profile(user_prompt)
        if onboarding_profile is not None:
            configured_slack_invite_link = integration_secrets.slack_invite_link.strip()
            configured_slack_token = integration_secrets.slack_api_key.strip()
            if configured_slack_invite_link or configured_slack_token:
                clear_pending_onboarding_session(req.session_id)
                try:
                    loop = asyncio.get_running_loop()
                    progress_queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

                    def on_onboarding_progress(event: dict[str, object]) -> None:
                        loop.call_soon_threadsafe(progress_queue.put_nowait, event)

                    workflow_task = asyncio.create_task(
                        run_onboarding_with_runtime_slack_token(
                            profile=onboarding_profile,
                            settings=settings,
                            client=client,
                            on_progress=on_onboarding_progress,
                        )
                    )

                    yield format_sse_payload(
                        {
                            "source": "onboarding",
                            "knowledge_sources": knowledge_sources,
                            "token": "",
                        }
                    )

                    while not workflow_task.done():
                        try:
                            progress_event = await asyncio.wait_for(
                                progress_queue.get(),
                                timeout=0.25,
                            )
                        except asyncio.TimeoutError:
                            continue

                        yield format_sse_payload(
                            {
                                "source": "onboarding",
                                "onboarding_progress": progress_event,
                                "knowledge_sources": knowledge_sources,
                                "token": "",
                            }
                        )

                    result = await workflow_task

                    while True:
                        try:
                            progress_event = progress_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                        yield format_sse_payload(
                            {
                                "source": "onboarding",
                                "onboarding_progress": progress_event,
                                "knowledge_sources": knowledge_sources,
                                "token": "",
                            }
                        )

                    for chunk in iter_text_chunks(result.report):
                        yield format_sse_payload({"token": chunk})
                    yield done_sse_payload()
                    return
                except Exception as exc:
                    error_message = f"온보딩 자동화 실행 실패: {exc}"
                    yield format_sse_payload({"source": "onboarding", "token": error_message})
                    yield done_sse_payload()
                    return

            set_pending_onboarding_session(req.session_id, onboarding_profile)
            onboarding_prompt = build_onboarding_token_request_message(onboarding_profile)
            yield format_sse_payload(
                {
                    "source": "onboarding",
                    "knowledge_sources": knowledge_sources,
                    "token": "",
                }
            )
            for chunk in iter_text_chunks(onboarding_prompt):
                yield format_sse_payload({"token": chunk})
            yield done_sse_payload()
            return

        pending_onboarding = get_pending_onboarding_session(req.session_id)
        if pending_onboarding is not None:
            if is_onboarding_cancel_command(user_prompt):
                clear_pending_onboarding_session(req.session_id)
                yield format_sse_payload(
                    {
                        "source": "onboarding",
                        "knowledge_sources": knowledge_sources,
                        "token": "",
                    }
                )
                for chunk in iter_text_chunks(build_onboarding_cancel_message()):
                    yield format_sse_payload({"token": chunk})
                yield done_sse_payload()
                return

            submitted_invite_link = extract_slack_invite_link(user_prompt)
            submitted_token = extract_slack_token(user_prompt)
            if not submitted_invite_link and not submitted_token:
                yield format_sse_payload(
                    {
                        "source": "onboarding",
                        "knowledge_sources": knowledge_sources,
                        "token": "",
                    }
                )
                for chunk in iter_text_chunks(build_onboarding_token_missing_message()):
                    yield format_sse_payload({"token": chunk})
                yield done_sse_payload()
                return

            if submitted_token:
                token_valid, token_detail = await validate_slack_invite_token(
                    submitted_token,
                    settings,
                )
                if not token_valid:
                    yield format_sse_payload(
                        {
                            "source": "onboarding",
                            "knowledge_sources": knowledge_sources,
                            "token": "",
                        }
                    )
                    for chunk in iter_text_chunks(
                        build_onboarding_token_invalid_message(token_detail)
                    ):
                        yield format_sse_payload({"token": chunk})
                    yield done_sse_payload()
                    return

            try:
                loop = asyncio.get_running_loop()
                progress_queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

                def on_onboarding_progress(event: dict[str, object]) -> None:
                    loop.call_soon_threadsafe(progress_queue.put_nowait, event)

                workflow_task = asyncio.create_task(
                    run_onboarding_with_runtime_slack_token(
                        profile=pending_onboarding.profile,
                        slack_token=submitted_token if submitted_token else None,
                        slack_invite_link=(
                            submitted_invite_link
                            if submitted_invite_link is not None
                            else None
                        ),
                        settings=settings,
                        client=client,
                        on_progress=on_onboarding_progress,
                    )
                )

                yield format_sse_payload(
                    {
                        "source": "onboarding",
                        "knowledge_sources": knowledge_sources,
                        "token": "",
                    }
                )

                while not workflow_task.done():
                    try:
                        progress_event = await asyncio.wait_for(
                            progress_queue.get(),
                            timeout=0.25,
                        )
                    except asyncio.TimeoutError:
                        continue

                    yield format_sse_payload(
                        {
                            "source": "onboarding",
                            "onboarding_progress": progress_event,
                            "knowledge_sources": knowledge_sources,
                            "token": "",
                        }
                    )

                result = await workflow_task
                clear_pending_onboarding_session(req.session_id)

                while True:
                    try:
                        progress_event = progress_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    yield format_sse_payload(
                        {
                            "source": "onboarding",
                            "onboarding_progress": progress_event,
                            "knowledge_sources": knowledge_sources,
                            "token": "",
                        }
                    )

                for chunk in iter_text_chunks(result.report):
                    yield format_sse_payload({"token": chunk})
                yield done_sse_payload()
                return
            except Exception as exc:
                error_message = (
                    f"온보딩 자동화 실행 실패: {exc}\\n"
                    "초대 링크(또는 관리자 토큰)를 다시 입력하거나 '취소'를 입력해 주세요."
                )
                yield format_sse_payload({"source": "onboarding", "token": error_message})
                yield done_sse_payload()
                return

        if settings.crewai_enabled and should_route_to_crewai(user_prompt):
            try:
                loop = asyncio.get_running_loop()
                progress_queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

                def on_crewai_progress(event: dict[str, object]) -> None:
                    loop.call_soon_threadsafe(progress_queue.put_nowait, event)

                crew_task = asyncio.create_task(
                    run_crewai_report(
                        user_prompt,
                        settings,
                        company_context,
                        on_progress=on_crewai_progress,
                    )
                )

                yield format_sse_payload(
                    {
                        "source": "crewai",
                        "knowledge_sources": knowledge_sources,
                        "token": "",
                    }
                )

                while not crew_task.done():
                    try:
                        progress_event = await asyncio.wait_for(
                            progress_queue.get(),
                            timeout=0.25,
                        )
                    except asyncio.TimeoutError:
                        continue

                    payload: dict[str, object] = {
                        "source": "crewai",
                        "knowledge_sources": knowledge_sources,
                        "crew_progress": progress_event,
                        "token": "",
                    }
                    graph_payload = progress_event.get("crew_graph")
                    if isinstance(graph_payload, dict):
                        payload["crew_graph"] = graph_payload

                    yield format_sse_payload(payload)

                crew_report, crew_graph = await crew_task

                while True:
                    try:
                        progress_event = progress_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                    payload: dict[str, object] = {
                        "source": "crewai",
                        "knowledge_sources": knowledge_sources,
                        "crew_progress": progress_event,
                        "token": "",
                    }
                    graph_payload = progress_event.get("crew_graph")
                    if isinstance(graph_payload, dict):
                        payload["crew_graph"] = graph_payload

                    yield format_sse_payload(payload)

                yield format_sse_payload(
                    {
                        "source": "crewai",
                        "crew_graph": crew_graph,
                        "knowledge_sources": knowledge_sources,
                        "token": "",
                    }
                )
                for chunk in iter_text_chunks(crew_report):
                    yield format_sse_payload({"token": chunk})
                yield done_sse_payload()
                return
            except Exception as exc:
                print(f"⚠️ CrewAI failed in /chat/stream, using default LLM fallback: {exc}")

        yield format_sse_payload(
            {
                "source": "llm",
                "knowledge_sources": knowledge_sources,
                "token": "",
            }
        )
        stream = await client.chat.completions.create(
            model=settings.llm_model,
            messages=inject_company_context(req.messages, company_context),
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                # SSE payload is JSON-encoded to preserve newlines and special chars.
                yield format_sse_payload({"token": delta})
        yield done_sse_payload()

    return StreamingResponse(
        token_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )
