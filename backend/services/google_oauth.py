from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import html
import importlib
import json
from pathlib import Path
import time
from urllib.parse import urlparse

from fastapi.responses import HTMLResponse
import httpx

from config import Settings
from onboarding_workflow import (
    IntegrationSecrets,
    looks_like_google_oauth_token,
    mask_secret,
    utc_now_iso,
)


GOOGLE_OAUTH_REQUESTED_SCOPES = (
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/gmail.send",
)

GOOGLE_OAUTH_STATE_TTL_SECONDS = 600
GOOGLE_OAUTH_TOKEN_REFRESH_GRACE_SECONDS = 60


@dataclass
class GoogleOAuthClientConfig:
    client_type: str
    client_id: str
    client_secret: str
    auth_uri: str
    token_uri: str
    redirect_uri: str
    redirect_uris: list[str]
    project_id: str | None = None


def prune_google_oauth_states(state_store: dict[str, float]) -> None:
    now = time.time()
    for state_key, expires_at in list(state_store.items()):
        if expires_at <= now:
            state_store.pop(state_key, None)


def resolve_google_oauth_token_file(settings: Settings) -> Path:
    configured_path = settings.google_oauth_token_path.strip()
    if configured_path:
        raw_path = Path(configured_path)
    else:
        raw_path = Path("./data/oauth/token.json")

    if raw_path.is_absolute():
        return raw_path

    return (Path(__file__).resolve().parent.parent / raw_path).resolve()


def import_google_oauth_runtime() -> tuple[object, object, object]:
    try:
        requests_module = importlib.import_module("google.auth.transport.requests")
        credentials_module = importlib.import_module("google.oauth2.credentials")
        flow_module = importlib.import_module("google_auth_oauthlib.flow")

        GoogleAuthRequest = getattr(requests_module, "Request")
        Credentials = getattr(credentials_module, "Credentials")
        InstalledAppFlow = getattr(flow_module, "InstalledAppFlow")
    except Exception as exc:
        raise RuntimeError(
            "google-auth-oauthlib/google-auth 패키지가 필요합니다. "
            "backend/requirements.txt 설치 후 다시 시도해 주세요."
        ) from exc

    return GoogleAuthRequest, Credentials, InstalledAppFlow


def parse_google_scope_values(scope_raw: object) -> list[str]:
    if isinstance(scope_raw, str):
        return sorted({scope.strip() for scope in scope_raw.split(" ") if scope.strip()})

    if isinstance(scope_raw, list):
        return sorted(
            {
                str(scope).strip()
                for scope in scope_raw
                if isinstance(scope, str) and str(scope).strip()
            }
        )

    return []


def parse_expires_in_seconds(expires_in_raw: object) -> int | None:
    if isinstance(expires_in_raw, int):
        return max(0, expires_in_raw)
    if isinstance(expires_in_raw, float):
        return max(0, int(expires_in_raw))
    if isinstance(expires_in_raw, str):
        stripped = expires_in_raw.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def compute_expires_in_seconds_from_datetime(expiry: object) -> int | None:
    if not isinstance(expiry, datetime):
        return None

    current = datetime.now(timezone.utc)
    normalized_expiry = expiry
    if normalized_expiry.tzinfo is None:
        normalized_expiry = normalized_expiry.replace(tzinfo=timezone.utc)

    seconds = int((normalized_expiry - current).total_seconds())
    return max(0, seconds)


def persist_google_credentials_to_file(token_file: Path, credentials: object) -> None:
    to_json = getattr(credentials, "to_json", None)
    if not callable(to_json):
        raise RuntimeError("OAuth credentials 직렬화에 실패했습니다.")

    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(str(to_json()), encoding="utf-8")


def load_google_credentials_from_file(token_file: Path) -> object | None:
    if not token_file.exists():
        return None

    _, Credentials, _ = import_google_oauth_runtime()
    try:
        return Credentials.from_authorized_user_file(
            str(token_file),
            scopes=list(GOOGLE_OAUTH_REQUESTED_SCOPES),
        )
    except Exception as exc:
        raise RuntimeError(f"OAuth token 파일 로드 실패: {exc}") from exc


def should_sync_google_oauth_store(secrets_store: IntegrationSecrets) -> bool:
    key = secrets_store.google_api_key.strip()
    return (not key) or looks_like_google_oauth_token(key)


def sync_google_access_token_from_token_file(
    token_file: Path,
    secrets_store: IntegrationSecrets,
) -> dict[str, object]:
    if not token_file.exists():
        return {"synced": False, "reason": "token-file-missing"}

    GoogleAuthRequest, _, _ = import_google_oauth_runtime()
    credentials = load_google_credentials_from_file(token_file)
    if credentials is None:
        return {"synced": False, "reason": "token-file-missing"}

    refresh_token = str(getattr(credentials, "refresh_token", "") or "").strip()
    valid = bool(getattr(credentials, "valid", False))
    access_token = str(getattr(credentials, "token", "") or "").strip()
    expires_in_seconds = compute_expires_in_seconds_from_datetime(
        getattr(credentials, "expiry", None)
    )

    should_refresh = bool(refresh_token) and (
        (not valid)
        or (not access_token)
        or (
            expires_in_seconds is not None
            and expires_in_seconds <= GOOGLE_OAUTH_TOKEN_REFRESH_GRACE_SECONDS
        )
    )
    if should_refresh:
        try:
            credentials.refresh(GoogleAuthRequest())
            persist_google_credentials_to_file(token_file, credentials)
        except Exception as exc:
            return {"synced": False, "error": f"OAuth token 자동 갱신 실패: {exc}"}

        access_token = str(getattr(credentials, "token", "") or "").strip()
        expires_in_seconds = compute_expires_in_seconds_from_datetime(
            getattr(credentials, "expiry", None)
        )

    if not access_token:
        return {"synced": False, "error": "OAuth token 파일에 access_token이 없습니다."}

    granted_scopes = parse_google_scope_values(getattr(credentials, "scopes", []))
    secrets_store.google_api_key = access_token
    secrets_store.updated_at = utc_now_iso()

    return {
        "synced": True,
        "access_token": access_token,
        "access_token_masked": mask_secret(access_token),
        "token_type": "Bearer",
        "expires_in_seconds": expires_in_seconds,
        "granted_scopes": granted_scopes,
    }


def persist_google_credentials_from_token_payload(
    *,
    token_file: Path,
    client: GoogleOAuthClientConfig,
    token_payload: dict[str, object],
    granted_scopes: list[str],
    expires_in_seconds: int | None,
) -> str | None:
    try:
        _, Credentials, _ = import_google_oauth_runtime()
    except RuntimeError as exc:
        return str(exc)

    refresh_token = str(token_payload.get("refresh_token", "") or "").strip()
    if not refresh_token:
        try:
            existing_credentials = load_google_credentials_from_file(token_file)
        except Exception:
            existing_credentials = None
        if existing_credentials is not None:
            refresh_token = str(
                getattr(existing_credentials, "refresh_token", "") or ""
            ).strip()

    access_token = str(token_payload.get("access_token", "") or "").strip()
    if not access_token:
        return "OAuth token 파일 저장 실패: access_token이 비어 있습니다."

    scopes = granted_scopes if granted_scopes else list(GOOGLE_OAUTH_REQUESTED_SCOPES)
    credentials = Credentials(
        token=access_token,
        refresh_token=refresh_token or None,
        token_uri=client.token_uri,
        client_id=client.client_id,
        client_secret=client.client_secret,
        scopes=scopes,
    )

    if expires_in_seconds is not None:
        credentials.expiry = datetime.now(timezone.utc) + timedelta(
            seconds=expires_in_seconds
        )

    try:
        persist_google_credentials_to_file(token_file, credentials)
    except Exception as exc:
        return f"OAuth token 파일 저장 실패: {exc}"

    return None


def issue_google_token_with_installed_flow(
    *,
    client: GoogleOAuthClientConfig,
    token_file: Path,
    port: int,
) -> dict[str, object]:
    _, _, InstalledAppFlow = import_google_oauth_runtime()

    client_config = {
        "installed": {
            "client_id": client.client_id,
            "client_secret": client.client_secret,
            "auth_uri": client.auth_uri,
            "token_uri": client.token_uri,
            "redirect_uris": client.redirect_uris,
        }
    }

    flow = InstalledAppFlow.from_client_config(
        client_config,
        list(GOOGLE_OAUTH_REQUESTED_SCOPES),
    )
    credentials = flow.run_local_server(
        host="localhost",
        port=port,
        open_browser=True,
        authorization_prompt_message=(
            "브라우저에서 Google 로그인/권한 동의를 완료해 주세요."
        ),
        success_message="인증이 완료되었습니다. 이 창을 닫고 앱으로 돌아가세요.",
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )

    persist_google_credentials_to_file(token_file, credentials)

    access_token = str(getattr(credentials, "token", "") or "").strip()
    if not access_token:
        raise RuntimeError("Installed OAuth 발급 결과에 access_token이 없습니다.")

    granted_scopes = parse_google_scope_values(getattr(credentials, "scopes", []))
    expires_in_seconds = compute_expires_in_seconds_from_datetime(
        getattr(credentials, "expiry", None)
    )

    return {
        "access_token": access_token,
        "access_token_masked": mask_secret(access_token),
        "token_type": "Bearer",
        "expires_in_seconds": expires_in_seconds,
        "granted_scopes": granted_scopes,
    }


def parse_google_oauth_client_config(
    payload: dict[str, object],
    callback_uris: list[str],
) -> GoogleOAuthClientConfig:
    section_name: str | None = None
    section: dict[str, object] | None = None

    for candidate in ("web", "installed"):
        value = payload.get(candidate)
        if isinstance(value, dict):
            section_name = candidate
            section = value
            break

    if section is None:
        section_name = "direct"
        section = payload

    client_id = str(section.get("client_id", "")).strip()
    client_secret = str(section.get("client_secret", "")).strip()
    auth_uri = str(
        section.get("auth_uri", "https://accounts.google.com/o/oauth2/v2/auth")
    ).strip()
    token_uri = str(section.get("token_uri", "https://oauth2.googleapis.com/token")).strip()
    project_id_raw = section.get("project_id")
    project_id = str(project_id_raw).strip() if isinstance(project_id_raw, str) else None

    redirect_uris_raw = section.get("redirect_uris")
    redirect_uris: list[str] = []
    if isinstance(redirect_uris_raw, list):
        redirect_uris = [
            str(item).strip()
            for item in redirect_uris_raw
            if isinstance(item, str) and str(item).strip()
        ]

    if not client_id or not client_secret:
        raise ValueError("OAuth client JSON에서 client_id/client_secret을 찾지 못했습니다.")

    if not redirect_uris:
        raise ValueError("OAuth client JSON에 redirect_uris가 없습니다.")

    def _is_loopback_redirect(uri: str) -> bool:
        try:
            parsed = urlparse(uri)
        except Exception:
            return False
        host = (parsed.hostname or "").strip().lower()
        return host in {"localhost", "127.0.0.1", "::1"}

    if section_name == "installed":
        # Installed/Desktop client는 run_local_server 기반으로 인증하므로
        # backend callback URI 매칭 없이 JSON의 loopback redirect URI를 그대로 사용한다.
        redirect_uri = redirect_uris[0]
    else:
        callback_candidates: list[str] = []
        for candidate in callback_uris:
            normalized = str(candidate).strip().rstrip("/")
            if normalized and normalized not in callback_candidates:
                callback_candidates.append(normalized)

        if not callback_candidates:
            raise ValueError("내부 오류: callback URI 후보가 비어 있습니다.")

        redirect_uri = next(
            (uri for uri in redirect_uris if uri.rstrip("/") in callback_candidates),
            None,
        )
        if redirect_uri is None:
            expected_list = ", ".join(callback_candidates)
            found_uris = ", ".join(redirect_uris)
            loopback_only = all(_is_loopback_redirect(uri) for uri in redirect_uris)
            if loopback_only:
                raise ValueError(
                    "현재 업로드한 JSON은 web 타입 + localhost(loopback) redirect URI 구성입니다. "
                    "이 경우 두 가지 중 하나로 진행해 주세요. "
                    "1) Web 방식 유지: Google Console Authorized redirect URI에 서버 callback URI를 추가. "
                    "2) localhost 자동 발급 방식: Desktop(Installed) OAuth client를 새로 생성 후 installed JSON 업로드. "
                    f"요청되는 callback 후보: {expected_list}. "
                    f"JSON에 들어있는 redirect_uris: {found_uris}"
                )

            raise ValueError(
                "OAuth client JSON에 현재 서버 callback URI가 없습니다. "
                "Google Console Authorized redirect URI에 다음 후보 중 하나를 추가 후 JSON을 다시 업로드하세요: "
                f"{expected_list}. "
                "Installed/Desktop 방식으로 진행하려면 최상위에 installed 섹션이 있는 JSON을 업로드하세요. "
                f"JSON에 들어있는 redirect_uris: {found_uris}"
            )

    return GoogleOAuthClientConfig(
        client_type=section_name,
        client_id=client_id,
        client_secret=client_secret,
        auth_uri=auth_uri,
        token_uri=token_uri,
        redirect_uri=redirect_uri,
        redirect_uris=list(redirect_uris),
        project_id=project_id,
    )


def build_google_oauth_popup_html(
    success: bool,
    message: str,
    payload_extra: dict[str, object] | None = None,
) -> HTMLResponse:
    event_type = "google-oauth-success" if success else "google-oauth-error"
    event_payload: dict[str, object] = {
        "type": event_type,
        "message": message,
    }
    if payload_extra:
        event_payload.update(payload_extra)

    payload = json.dumps(event_payload, ensure_ascii=False)
    escaped_message = html.escape(message)
    status_label = "완료" if success else "실패"
    html_body = f"""<!doctype html>
<html lang=\"ko\">
  <head>
    <meta charset=\"utf-8\" />
    <title>Google OAuth {status_label}</title>
  </head>
  <body style=\"font-family: sans-serif; padding: 20px;\">
    <h2>Google OAuth {status_label}</h2>
    <p>{escaped_message}</p>
    <p>잠시 후 창이 닫힙니다.</p>
    <script>
      (function () {{
        try {{
          if (window.opener) {{
            window.opener.postMessage({payload}, "*");
          }}
        }} catch (e) {{}}
        setTimeout(function () {{ window.close(); }}, 500);
      }})();
    </script>
  </body>
</html>"""
    return HTMLResponse(content=html_body)


def extract_oauth_token_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        return ""

    if not isinstance(payload, dict):
        return ""

    error_value = payload.get("error")
    error_desc = payload.get("error_description")

    message_parts: list[str] = []
    if isinstance(error_value, str) and error_value.strip():
        message_parts.append(error_value.strip())
    if isinstance(error_desc, str) and error_desc.strip():
        message_parts.append(error_desc.strip())

    return " | ".join(message_parts)
