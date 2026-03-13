# API 레퍼런스

## 기본 정보

| 항목 | 값 |
|------|-----|
| Base URL | `http://localhost:8000` |
| 프로토콜 | REST (JSON) + SSE (Server-Sent Events) |
| 인증 | 없음 (내부 전용) |
| API 문서 | `http://localhost:8000/docs` (Swagger UI) |

---

## 목차

- [헬스체크](#헬스체크)
- [채팅](#채팅)
- [번역](#번역)
- [지식 베이스 (RAG)](#지식-베이스-rag)
- [통합 서비스 키](#통합-서비스-키)
- [Google OAuth](#google-oauth)
- [데이터 모델](#데이터-모델)
- [에러 처리](#에러-처리)

---

## 헬스체크

### `GET /health`

서버 상태 확인.

**Response** `200`
```json
{ "status": "ok" }
```

---

## 채팅

### `POST /chat`

비스트리밍 채팅. 온보딩/CrewAI/기본 LLM 중 자동 라우팅됩니다.

**Request Body**
```json
{
  "messages": [
    { "role": "user", "content": "2026년 IT 트렌드 분석해줘" }
  ],
  "session_id": "abc123",
  "stream": false
}
```

| 필드 | 타입 | 필수 | 제약 | 설명 |
|------|------|------|------|------|
| `messages` | `ChatMessage[]` | ✅ | 1~200개 | 대화 메시지 배열 |
| `messages[].role` | `string` | ✅ | `"user"` \| `"assistant"` \| `"system"` | 역할 |
| `messages[].content` | `string` | ✅ | 1~16,000자, null 문자 ✕ | 메시지 내용 |
| `session_id` | `string` | ❌ | 1~120자, 기본값 `"default"` | 세션 식별자 |
| `stream` | `boolean` | ❌ | 기본값 `false` | 미사용 (스트리밍은 별도 엔드포인트) |

**Response** `200`
```json
{
  "message": "# 2026년 IT 트렌드 보고서\n...",
  "session_id": "abc123",
  "source": "crewai",
  "crew_graph": { "topic": "...", "target_year": 2026, "agents": [...], "tasks": [...] },
  "knowledge_sources": [{ "document": "company.pdf", "excerpt": "..." }]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `message` | `string` | 응답 메시지 (마크다운) |
| `session_id` | `string` | 세션 ID |
| `source` | `string \| null` | 응답 소스: `"llm"`, `"crewai"`, `"onboarding"` |
| `crew_graph` | `object \| null` | CrewAI DAG 그래프 (CrewAI 응답 시) |
| `knowledge_sources` | `array \| null` | RAG 참조 문서 목록 |

---

### `POST /chat/stream`

SSE 스트리밍 채팅. Request Body는 `/chat`과 동일합니다.

**Response** `200 text/event-stream`

```
data: {"source": "crewai", "token": "", "crew_graph": {"topic": "IT 트렌드", "target_year": 2026, "agents": [...], "tasks": [...]}}\n\n
data: {"source": "crewai", "crew_progress": {"phase": "running", "active_task_id": "research", "active_agent_id": "researcher", "updated_at": "...", "tasks": [...]}}\n\n
data: {"source": "crewai", "token": "# 보고서 제목\n"}\n\n
data: {"source": "crewai", "token": "본문 텍스트..."}\n\n
data: [DONE]\n\n
```

#### SSE 이벤트 페이로드

**토큰 이벤트** (텍스트 청크, ~140자)
```json
{ "source": "llm|crewai|onboarding", "token": "텍스트 청크..." }
```

**CrewAI 그래프 이벤트** (최초 1회)
```json
{
  "source": "crewai",
  "token": "",
  "crew_graph": {
    "topic": "IT 트렌드",
    "target_year": 2026,
    "agents": [
      { "id": "researcher", "role": "Researcher", "goal": "..." }
    ],
    "tasks": [
      { "id": "research", "title": "Web Research", "agent_id": "researcher", "depends_on": [] }
    ]
  }
}
```

**CrewAI 진행 이벤트** (태스크 전환 시)
```json
{
  "source": "crewai",
  "crew_progress": {
    "phase": "running",
    "active_task_id": "trend_analysis",
    "active_agent_id": "trend_analyst",
    "updated_at": "2026-03-13T10:30:00Z",
    "tasks": [
      { "task_id": "research", "title": "Web Research", "agent_id": "researcher", "status": "completed" },
      { "task_id": "trend_analysis", "title": "Trend Analysis", "agent_id": "trend_analyst", "status": "running" }
    ]
  }
}
```

**온보딩 진행 이벤트**
```json
{ "source": "onboarding", "token": "[Drive 검색 중...]\n" }
```

**완료 이벤트**
```
data: [DONE]\n\n
```

#### 라우팅 우선순위

1. **온보딩** — `[이름] [부서] [날짜] [이메일]` 패턴 감지 시
2. **대기 세션** — 이전 온보딩 요청이 Slack 토큰 입력 대기 중일 때
3. **CrewAI** — 트렌드/조사/보고서/분석 키워드 감지 시
4. **기본 LLM** — 위 조건에 해당하지 않을 때 (RAG + Drive 컨텍스트 주입)

---

## 번역

### `POST /translate`

텍스트 번역 (마크다운 포맷 보존 옵션).

**Request Body**
```json
{
  "text": "# IT Trend Report 2026\n...",
  "target_language": "ko",
  "preserve_markdown": true
}
```

| 필드 | 타입 | 필수 | 제약 | 설명 |
|------|------|------|------|------|
| `text` | `string` | ✅ | 1~32,000자 | 번역할 텍스트 |
| `target_language` | `string` | ❌ | 2~40자, 기본값 `"ko"` | 목표 언어 |
| `preserve_markdown` | `boolean` | ❌ | 기본값 `true` | 마크다운 보존 여부 |

**Response** `200`
```json
{
  "translated_text": "# 2026년 IT 트렌드 보고서\n...",
  "target_language": "ko",
  "source": "llm"
}
```

---

## 지식 베이스 (RAG)

### `GET /knowledge/status`

RAG 상태 조회.

**Response** `200`
```json
{
  "rag_enabled": true,
  "chunk_count": 42,
  "documents": ["company_policy.pdf", "onboarding_guide.docx"],
  "updated_at": "2026-03-13T09:00:00Z"
}
```

---

### `POST /knowledge/upload`

문서 업로드 및 인덱싱.

**Request** `multipart/form-data`

| 필드 | 타입 | 제약 | 설명 |
|------|------|------|------|
| `file` | `File` | 최대 20MB (설정 가능) | 업로드 파일 |

**지원 형식:** PDF, DOCX, TXT, MD, CSV, JSON

**Response** `200`
```json
{
  "filename": "company_policy.pdf",
  "chunk_count": 15,
  "total_chunks": 42,
  "embedded": true,
  "documents": ["company_policy.pdf", "onboarding_guide.docx"],
  "updated_at": "2026-03-13T09:00:00Z"
}
```

| 필드 | 설명 |
|------|------|
| `chunk_count` | 이번 문서에서 생성된 청크 수 |
| `total_chunks` | 전체 지식 베이스 청크 수 |
| `embedded` | 임베딩 성공 여부 |
| `documents` | 전체 인덱싱된 문서 목록 |

---

## 통합 서비스 키

### `GET /integrations/env`

저장된 통합 키 상태 조회 (마스킹된 값 반환).

**Response** `200`
```json
{
  "has_google_api_key": true,
  "has_slack_api_key": false,
  "has_slack_invite_link": true,
  "google_api_key_masked": "ya29...abc",
  "slack_api_key_masked": null,
  "slack_invite_link_masked": "http...ken",
  "updated_at": "2026-03-13T09:00:00Z"
}
```

---

### `POST /integrations/env`

통합 키 업데이트. `null` 필드는 변경하지 않습니다.

**Request Body**
```json
{
  "google_api_key": "ya29...",
  "slack_api_key": null,
  "slack_invite_link": "https://join.slack.com/t/workspace/shared_invite/..."
}
```

| 필드 | 타입 | 제약 | 설명 |
|------|------|------|------|
| `google_api_key` | `string \| null` | 최대 4,096자 | Google OAuth 또는 API 키 |
| `slack_api_key` | `string \| null` | 최대 4,096자 | Slack 관리자 토큰 (xoxp-/xoxa-2-) |
| `slack_invite_link` | `string \| null` | 최대 4,096자 | Slack 공유 초대 URL |

**Response** `200` — `EnvSecretsStatusResponse` (GET과 동일 형식)

---

## Google OAuth

### `GET /integrations/google/oauth-client/status`

등록된 OAuth 클라이언트 상태 조회.

**Response** `200`
```json
{
  "configured": true,
  "client_type": "web",
  "project_id": "my-project-123",
  "client_id_masked": "1234...com",
  "redirect_uri": "http://localhost:8000/integrations/google/oauth/callback"
}
```

---

### `POST /integrations/google/oauth-client`

OAuth 클라이언트 JSON 업로드. Web App 또는 Installed 타입 지원.

**Request** `multipart/form-data`

| 필드 | 타입 | 제약 | 설명 |
|------|------|------|------|
| `file` | `File` | 최대 1MB | Google Cloud Console에서 다운로드한 JSON |

**Headers** (선택)

| 헤더 | 설명 |
|------|------|
| `X-Frontend-Origin` | 프론트엔드 origin (callback URI 매칭용) |

**Response** `200` — `GoogleOAuthClientStatusResponse`

---

### `DELETE /integrations/google/oauth-client`

OAuth 클라이언트 설정 및 state 초기화.

**Response** `200`
```json
{ "configured": false, "client_type": null, "project_id": null, "client_id_masked": null, "redirect_uri": null }
```

---

### `GET /integrations/google/oauth/start`

OAuth 인증 URL 생성 (Web App 전용).

**Response** `200`
```json
{
  "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=...&redirect_uri=...&scope=...&state=...",
  "expires_in_seconds": 600
}
```

**Error** `400` — Installed 타입이거나 OAuth 클라이언트 미등록

---

### `GET /integrations/google/oauth/callback`

OAuth 팝업 콜백 처리. 토큰 교환 후 HTML 팝업 반환.

**Query Parameters**

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `code` | `string` | Authorization code |
| `state` | `string` | State 토큰 |
| `error` | `string` | 오류 코드 (실패 시) |

**Response** `200 text/html` — 팝업에서 `window.opener.postMessage`로 결과 전달

---

### `POST /integrations/google/oauth/installed/issue`

Installed/Desktop OAuth 플로우 토큰 발급. 로컬 서버를 열어 브라우저 인증을 진행합니다.

**Response** `200`
```json
{
  "message": "Installed OAuth 발급이 완료되었습니다.",
  "access_token_masked": "ya29...abc",
  "token_type": "Bearer",
  "expires_in_seconds": 3599,
  "granted_scopes": ["openid", "drive.readonly", "gmail.send"]
}
```

---

### `GET /integrations/google/scope-status`

현재 OAuth 토큰의 스코프 상태 확인.

**Response** `200`
```json
{
  "token_configured": true,
  "token_type": "oauth_token",
  "granted_scopes": ["openid", "drive.readonly", "gmail.send"],
  "drive_scope_ready": true,
  "gmail_scope_ready": true,
  "drive_scope_hints": ["drive.readonly", "drive.metadata.readonly", "drive"],
  "gmail_scope_hints": ["gmail.send", "gmail.compose", "mail.google.com"],
  "tokeninfo_error": null
}
```

---

## 데이터 모델

### ChatMessage

```
role:    "user" | "assistant" | "system"  (필수)
content: string (1~16,000자, null/제어문자 불가)
```

### ChatRequest

```
messages:   ChatMessage[] (1~200개)
session_id: string (1~120자, 기본 "default")
stream:     boolean (기본 false)
```

### CrewGraph

```
topic:       string
target_year: number
agents:      CrewGraphAgent[]
tasks:       CrewGraphTask[]
```

### CrewGraphAgent

```
id:   string    (예: "researcher")
role: string    (예: "Researcher")
goal: string
```

### CrewGraphTask

```
id:              string    (예: "research")
title:           string    (예: "Web Research")
agent_id:        string    (담당 에이전트 ID)
depends_on:      string[]  (선행 태스크 ID 배열)
description?:    string
expected_output?: string
```

### CrewProgress

```
phase:           string    ("graph_ready" | "running" | "task_completed" | "crew_completed")
active_task_id:  string | null
active_agent_id: string | null
detail?:         string | null
updated_at:      string    (ISO 8601)
tasks:           CrewProgressTask[]
```

### CrewProgressTask

```
task_id:  string
title:    string
agent_id: string
status:   "pending" | "running" | "completed" | "failed"
```

---

## 에러 처리

### HTTP 상태 코드

| 코드 | 의미 |
|------|------|
| `400` | 잘못된 요청 (유효성 검증 실패, 누락된 파라미터) |
| `413` | 파일 크기 초과 |
| `422` | Pydantic 유효성 검증 실패 (FastAPI 자동) |
| `500` | 서버 내부 오류 |
| `502` | 외부 서비스 실패 (LLM, OAuth 토큰 교환 등) |

### 에러 응답 형식

```json
{ "detail": "에러 메시지" }
```

Pydantic 검증 실패 시 (422):
```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "messages", 0, "content"],
      "msg": "String should have at least 1 character",
      "input": ""
    }
  ]
}
```
