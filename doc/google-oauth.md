# Google OAuth 연동

## 개요

Google Drive 컨텍스트 검색과 Gmail 온보딩 이메일 발송을 위해 Google OAuth 2.0 인증이 필요합니다. Web App 플로우와 Installed App(데스크톱) 플로우 두 가지를 지원합니다.

---

## 파일 위치

```
backend/
├── services/
│   ├── google_oauth.py        # OAuth 클라이언트, 토큰 관리, 스코프 검증
│   └── drive_context.py       # Drive 파일 검색 + 텍스트 추출
├── main.py                    # OAuth 관련 6개 엔드포인트
└── data/
    └── oauth/
        └── token.json         # 영구 저장 토큰 (Installed 플로우)
```

---

## 요청 스코프

```python
GOOGLE_OAUTH_REQUESTED_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]
```

| 스코프 | 용도 |
|--------|------|
| `openid` | OpenID Connect 인증 |
| `userinfo.email` | 인증된 사용자 이메일 확인 |
| `drive.readonly` | Google Drive 파일 읽기 (채팅 컨텍스트, 온보딩 문서 검색) |
| `gmail.send` | 온보딩 이메일 발송 |

---

## OAuth 플로우

### 1. Web App 플로우 (팝업 방식)

Frontend에서 팝업 창을 열어 Google 인증을 진행합니다.

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐
│  Frontend   │     │   Backend   │     │   Google     │
│  (Tools)    │     │  (FastAPI)  │     │  OAuth 서버   │
└──────┬──────┘     └──────┬──────┘     └──────┬───────┘
       │                   │                   │
       │ 1. POST /oauth-client (JSON 업로드)    │
       │──────────────────>│                   │
       │                   │ 검증 + 저장        │
       │<──────────────────│                   │
       │                   │                   │
       │ 2. GET /oauth/start                    │
       │──────────────────>│                   │
       │      auth_url     │ state 토큰 생성    │
       │<──────────────────│                   │
       │                   │                   │
       │ 3. window.open(auth_url)               │
       │───────────────────────────────────────>│
       │                   │                   │
       │                   │ 4. 사용자 동의      │
       │                   │                   │
       │                   │ 5. callback (code + state)
       │                   │<──────────────────│
       │                   │                   │
       │                   │ 6. code → access_token 교환
       │                   │──────────────────>│
       │                   │<──────────────────│
       │                   │                   │
       │                   │ 7. 토큰 저장       │
       │                   │ HTML 팝업 반환     │
       │                   │                   │
       │ 8. window.postMessage (결과)           │
       │<──────────────────│                   │
       │                   │                   │
       │ 9. 팝업 닫기 + 상태 갱신               │
       │                   │                   │
```

**보안 조치:**
- State 토큰: `secrets.token_urlsafe(24)` (24바이트)
- TTL: 600초 (10분)
- 주기적 pruning으로 만료된 state 정리

### 2. Installed App 플로우 (데스크톱 방식)

로컬 HTTP 서버를 열어 인증을 처리합니다. `token.json`에 refresh_token이 저장되어 자동 갱신됩니다.

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐
│  Frontend   │     │   Backend   │     │   Google     │
│  (Tools)    │     │  (FastAPI)  │     │  OAuth 서버   │
└──────┬──────┘     └──────┬──────┘     └──────┬───────┘
       │                   │                   │
       │ 1. POST /oauth-client (installed JSON)│
       │──────────────────>│                   │
       │                   │                   │
       │ 2. POST /oauth/installed/issue        │
       │──────────────────>│                   │
       │                   │                   │
       │                   │ 3. 로컬 서버 시작   │
       │                   │    (localhost:8080)│
       │                   │                   │
       │                   │ 4. 브라우저 자동 오픈│
       │                   │──────────────────>│
       │                   │                   │
       │                   │ 5. 사용자 동의      │
       │                   │                   │
       │                   │ 6. callback → 토큰 │
       │                   │<──────────────────│
       │                   │                   │
       │                   │ 7. token.json 저장 │
       │   결과 반환        │                   │
       │<──────────────────│                   │
```

**특징:**
- `google-auth-oauthlib`의 `InstalledAppFlow` 사용
- `refresh_token` 포함 → 만료 시 자동 갱신
- 포트: `GOOGLE_OAUTH_INSTALLED_PORT` (기본 8080)

---

## 클라이언트 설정

### GoogleOAuthClientConfig

```python
@dataclass
class GoogleOAuthClientConfig:
    client_type: str       # "web" 또는 "installed"
    client_id: str
    client_secret: str
    auth_uri: str
    token_uri: str
    project_id: str | None
    redirect_uri: str | None   # Web 전용
```

### 클라이언트 JSON 형식

**Web App:**
```json
{
  "web": {
    "client_id": "123...apps.googleusercontent.com",
    "client_secret": "GOCSPX-...",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "redirect_uris": ["http://localhost:8000/integrations/google/oauth/callback"],
    "project_id": "my-project"
  }
}
```

**Installed:**
```json
{
  "installed": {
    "client_id": "123...apps.googleusercontent.com",
    "client_secret": "GOCSPX-...",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "project_id": "my-project"
  }
}
```

### Redirect URI 매칭

Web App 클라이언트 업로드 시 redirect_uri를 자동 매칭합니다:

1. `X-Frontend-Origin` 헤더의 hostname + 백엔드 포트
2. 백엔드 base_url
3. `localhost` ↔ `127.0.0.1` 양방향 매칭

---

## 토큰 관리

### 인메모리 저장

`app.state.integration_secrets.google_api_key`에 access_token이 저장됩니다.

### 파일 영구 저장 (`token.json`)

Installed 플로우 또는 Web 플로우(refresh_token 포함 시)에서 `token.json`에 저장됩니다.

```json
{
  "token": "ya29...",
  "refresh_token": "1//...",
  "token_uri": "https://oauth2.googleapis.com/token",
  "client_id": "123...apps.googleusercontent.com",
  "client_secret": "GOCSPX-...",
  "scopes": ["openid", "drive.readonly", "gmail.send"],
  "expiry": "2026-03-13T11:00:00Z"
}
```

### 자동 갱신

서버 시작 시 및 API 호출 시 `sync_google_access_token_from_token_file()`이 실행됩니다:

1. `token.json` 존재 확인
2. 만료 시간 확인 (60초 grace period)
3. 만료 임박 시 refresh_token으로 갱신
4. `integration_secrets.google_api_key`에 새 토큰 동기화

---

## 스코프 검증

### `GET /integrations/google/scope-status`

현재 토큰의 스코프 상태를 확인합니다.

**Drive 스코프 힌트:**
```python
DRIVE_SCOPE_HINTS = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/drive",
]
```

**Gmail 스코프 힌트:**
```python
GMAIL_SCOPE_HINTS = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://mail.google.com/",
]
```

### 스코프 확인 로직

```python
has_any_required_scope(granted_scopes, required_hints) -> bool
# granted_scopes 중 하나라도 required_hints에 포함되면 True
```

---

## Google Drive 컨텍스트 (drive_context.py)

### 개요

OAuth 인증 후 사용자의 Google Drive에서 쿼리 관련 파일을 자동으로 검색하여 채팅 컨텍스트에 주입합니다.

### 검색 흐름

```
사용자 쿼리
    │
    ▼
키워드 추출 (최대 4개)
    │
    ▼
Google Drive Files API
    fullText contains '키워드'
    trashed = false
    orderBy: modifiedTime desc
    │
    ▼
파일 다운로드 / Export
    ├→ Google Docs  → Export as text/plain
    ├→ Google Sheets → Export as text/csv
    ├→ Google Slides → Export as text/plain
    └→ 기타 (PDF, DOCX, TXT...) → 직접 다운로드
    │
    ▼
텍스트 발췌 (최대 1400자/파일)
    │
    ▼
[Google Drive Shared Files] 컨텍스트로 주입
```

### MIME 타입 처리

| Google MIME | Export 형식 |
|-------------|------------|
| `application/vnd.google-apps.document` | `text/plain` |
| `application/vnd.google-apps.spreadsheet` | `text/csv` |
| `application/vnd.google-apps.presentation` | `text/plain` |

직접 다운로드 허용 MIME: `text/*`, `.pdf`, `.docx`, `.csv`, `.json`

### 설정

| 환경 변수 | 기본값 | 범위 | 설명 |
|-----------|--------|------|------|
| `GOOGLE_DRIVE_CONTEXT_ENABLED` | `true` | - | Drive 컨텍스트 활성화 |
| `GOOGLE_DRIVE_CONTEXT_RESULTS` | `4` | 1~12 | 검색 결과 수 |
| `GOOGLE_DRIVE_CONTEXT_MAX_CHARS` | `1400` | 300~6,000 | 파일당 최대 발췌 문자 |
| `GOOGLE_DRIVE_CONTEXT_MAX_FILE_BYTES` | `4,000,000` | 100KB~20MB | 파일 최대 크기 |

---

## API 엔드포인트 요약

| Method | Endpoint | 설명 |
|--------|----------|------|
| `GET` | `/integrations/google/oauth-client/status` | OAuth 클라이언트 상태 |
| `POST` | `/integrations/google/oauth-client` | 클라이언트 JSON 업로드 |
| `DELETE` | `/integrations/google/oauth-client` | 클라이언트 설정 초기화 |
| `GET` | `/integrations/google/oauth/start` | 인증 URL 생성 (Web) |
| `GET` | `/integrations/google/oauth/callback` | OAuth 콜백 (Web) |
| `POST` | `/integrations/google/oauth/installed/issue` | 토큰 발급 (Installed) |
| `GET` | `/integrations/google/scope-status` | 스코프 상태 확인 |

---

## 설정

| 환경 변수 | 기본값 | 설명 |
|-----------|--------|------|
| `GOOGLE_API_KEY` | `""` | OAuth access_token 또는 API 키 |
| `GOOGLE_OAUTH_TOKEN_PATH` | `./data/oauth/token.json` | 토큰 파일 경로 |
| `GOOGLE_OAUTH_INSTALLED_PORT` | `8080` | Installed 플로우 로컬 서버 포트 |

---

## Frontend UI (ToolsPage)

Tools 페이지에서 OAuth 설정을 관리합니다:

1. **OAuth 클라이언트 JSON 업로드** — 드래그앤드롭 또는 파일 선택
2. **클라이언트 타입 표시** — Web / Installed 자동 감지
3. **인증 시작** — Web: 팝업 열기 / Installed: key 발급 버튼
4. **스코프 상태** — Drive/Gmail 스코프 준비 여부 표시
5. **5단계 시각화** — 업로드 → 설정 확인 → 인증 → 토큰 저장 → 완료

### 팝업 통신 (Web 플로우)

```javascript
// Frontend: 팝업 결과 수신
window.addEventListener("message", (event) => {
  if (event.data?.flow_step === "token-saved") {
    // 스코프 상태 새로고침
  }
});
```
