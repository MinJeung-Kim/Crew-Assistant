# 시스템 아키텍처

## 개요

Orchestration은 FastAPI 백엔드와 React 프론트엔드로 구성된 풀스택 멀티 에이전트 AI 플랫폼입니다. CrewAI 기반 트렌드 리서치, 회사 문서 RAG, 신규 직원 온보딩 자동화, 실시간 SSE 스트리밍 채팅을 하나의 통합 인터페이스로 제공합니다.

---

## 전체 시스템 다이어그램

```
┌──────────────────────────────────────────────────────────────┐
│                    Frontend (React 19)                        │
│                                                              │
│  ┌──────────┐  ┌─────────────┐  ┌──────────────────────────┐│
│  │  Chat UI │  │  CrewFlow   │  │  Tools (Integrations)    ││
│  │ 스트리밍  │  │  DAG 시각화  │  │  OAuth / Slack / Env    ││
│  └────┬─────┘  └──────┬──────┘  └────────────┬─────────────┘│
│       │               │                      │               │
│       └───────────────┼──────────────────────┘               │
│                       │                                      │
│              SSE Stream / REST API                            │
└───────────────────────┼──────────────────────────────────────┘
                        │ HTTP (CORS)
┌───────────────────────┼──────────────────────────────────────┐
│                 Backend (FastAPI + Uvicorn)                    │
│                       │                                      │
│              ┌────────┴─────────┐                            │
│              │   Request Router  │                            │
│              │                  │                             │
│              │  1. Onboarding?  │                             │
│              │  2. Pending Sess?│                             │
│              │  3. CrewAI?      │                             │
│              │  4. Default LLM  │                             │
│              └──┬──────┬──────┬─┘                            │
│                 │      │      │                               │
│  ┌──────────────┤      │      ├──────────────────┐           │
│  │              │      │      │                  │           │
│  ▼              ▼      ▼      ▼                  ▼           │
│ ┌────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │
│ │CrewAI  │ │  RAG   │ │Onboarding│ │ Google   │ │Streaming│ │
│ │Planning│ │Hybrid  │ │Workflow  │ │ OAuth    │ │  SSE   │ │
│ │Routing │ │Search  │ │Gmail+    │ │Token Mgmt│ │Format  │ │
│ │Execute │ │Embedding│ │Slack+   │ │Scope Chk │ │Chunking│ │
│ └───┬────┘ └───┬────┘ │Drive    │ └──────────┘ └────────┘ │
│     │          │      └────┬────┘                           │
│     │          │           │                                │
└─────┼──────────┼───────────┼────────────────────────────────┘
      │          │           │
      ▼          ▼           ▼
┌──────────┐ ┌────────┐ ┌─────────────────┐
│ DuckDuck │ │ OpenAI │ │ Google APIs     │
│ Go Search│ │  LLM   │ │ Drive / Gmail   │
│          │ │Embedding│ │ OAuth2 / Token  │
└──────────┘ └────────┘ └─────────────────┘
```

---

## 레이어 아키텍처

### 1. Presentation Layer (Frontend)

| 모듈 | 역할 |
|------|------|
| `ChatUI` | 채팅 워크스페이스 메인 라우터 + 레이아웃 |
| `useChat` Hook | 메시지 상태, SSE 구독, AbortController 관리 |
| `chatStream` Service | SSE 청크 파싱 + 타입 가드 |
| `CrewFlowPage` | @xyflow/react 기반 DAG 시각화 |
| `ToolsPage` | OAuth 플로우 + 통합 설정 UI |

### 2. API Layer (FastAPI)

| 모듈 | 역할 |
|------|------|
| `main.py` | 엔드포인트 정의 + 요청 라우팅 + Pydantic 모델 |
| CORS Middleware | `cors_origins_list` 기반 교차 출처 허용 |
| Lifespan | `app.state` 초기화 (LLM client, KB, Secrets, OAuth) |

### 3. Service Layer

| 모듈 | 역할 |
|------|------|
| `chat_service.py` | LLM 호출, 번역, CrewAI 위임, 컨텍스트 로딩 |
| `google_oauth.py` | OAuth 클라이언트 설정, 토큰 관리, 스코프 검증 |
| `drive_context.py` | Google Drive 파일 검색 + 텍스트 추출 |
| `streaming.py` | SSE 페이로드 포맷 + 텍스트 청크 분할 |

### 4. Domain Layer

| 모듈 | 역할 |
|------|------|
| `crew/` | CrewAI 에이전트 계획 → 라우팅 → 실행 → 포맷팅 |
| `knowledge_base.py` | RAG 청킹 → 임베딩 → 하이브리드 검색 |
| `onboarding_workflow.py` | 프로필 파싱 → Drive/Gmail/Slack 자동화 |

### 5. Infrastructure Layer

| 리소스 | 역할 |
|--------|------|
| `config.py` | Pydantic Settings `.env` 바인딩 |
| `data/knowledge/` | RAG JSON 인덱스 저장소 |
| `data/oauth/` | Google OAuth `token.json` 파일 |

---

## 요청 라우팅 흐름

`POST /chat/stream` 요청이 들어오면 다음 순서로 라우팅됩니다:

```
사용자 메시지
    │
    ▼
┌─────────────────────────────┐
│ 1. 온보딩 프로필 감지?       │  이름 부서 날짜 이메일 패턴
│    parse_onboarding_profile │
├─────────────────────────────┤
│ YES → 온보딩 워크플로우 시작  │  Slack 토큰/초대링크 확인 후 실행
│ NO  → 다음 단계              │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ 2. 대기 중인 세션?           │  Slack 토큰 입력 대기 상태
│    pending_onboarding_by_   │
│    session 확인              │
├─────────────────────────────┤
│ YES → 토큰 검증 → 워크플로우 │
│ NO  → 다음 단계              │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ 3. CrewAI 키워드 감지?       │  트렌드/조사/보고서/분석 등
│    should_route_to_crewai   │
├─────────────────────────────┤
│ YES → CrewAI 멀티 에이전트   │  동적 에이전트 구성 → 실행
│ NO  → 다음 단계              │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ 4. 기본 LLM 채팅             │  RAG + Drive 컨텍스트 주입
│    run_default_llm_chat     │
└─────────────────────────────┘
```

---

## SSE 스트리밍 프로토콜

모든 실시간 응답은 Server-Sent Events (SSE) 프로토콜로 전송됩니다.

### 페이로드 형식

```
data: {"source": "llm", "token": "응답 텍스트 청크..."}\n\n
data: {"source": "crewai", "token": "...", "crew_graph": {...}}\n\n
data: {"source": "crewai", "crew_progress": {...}}\n\n
data: {"source": "onboarding", "token": "..."}\n\n
data: [DONE]\n\n
```

### SSE 이벤트 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `source` | `string` | 응답 소스: `"llm"`, `"crewai"`, `"onboarding"` |
| `token` | `string` | 텍스트 청크 (~140자) |
| `crew_graph` | `object` | CrewAI DAG 그래프 (최초 1회) |
| `crew_progress` | `object` | 태스크 진행 상황 업데이트 |

### 프론트엔드 파싱 흐름

```
ReadableStream
    → chunk (Uint8Array → text)
    → parseSseChunk(rawChunk, pendingBuffer)
    → 줄 단위 분할: "data: " prefix → payload 추출
    → parseSsePayload(payload)
        → "[DONE]" → done=true
        → JSON.parse → 타입 가드 → ParsedChatStreamEvent
    → 미완성 줄 → pendingBuffer 유지
```

---

## 상태 관리

### Backend (`app.state`)

| 키 | 타입 | 설명 |
|----|------|------|
| `llm_client` | `AsyncOpenAI` | LLM 커넥션 (lifespan에서 초기화) |
| `knowledge_base` | `CompanyKnowledgeBase` | RAG 인스턴스 |
| `integration_secrets` | `IntegrationSecrets` | Google/Slack 키 저장소 |
| `google_oauth_client` | `GoogleOAuthClientConfig \| None` | OAuth 클라이언트 설정 |
| `google_oauth_states` | `dict[str, ...]` | OAuth state 토큰 (TTL 10분) |
| `google_oauth_token_file` | `Path` | token.json 경로 |
| `pending_onboarding_by_session` | `dict[str, PendingOnboardingSession]` | 온보딩 대기 세션 (TTL 10분) |

### Frontend (React State)

| Hook/State | 설명 |
|------------|------|
| `useChat.messages` | 대화 메시지 배열 (`Message[]`) |
| `useChat.crewGraph` | CrewAI DAG 그래프 (`CrewGraph \| null`) |
| `useChat.crewProgress` | 태스크 진행 상황 (`CrewProgress \| null`) |
| `useChat.isStreaming` | 스트리밍 중 여부 |
| `useChat.error` | 오류 메시지 |
| `useChat.abortController` | SSE 중단 컨트롤러 |

---

## 보안 설계

| 영역 | 구현 |
|------|------|
| **CORS** | 설정된 origin만 허용 (`cors_origins_list`) |
| **입력 검증** | Pydantic 모델 + `field_validator` (역할 enum, 메시지 크기, 제어문자 거부) |
| **비밀키 마스킹** | `mask_secret()`: 앞 4자 + `...` + 뒤 3자 |
| **OAuth State** | `secrets.token_urlsafe(24)` + 10분 TTL + 주기적 pruning |
| **XSS 방지** | `react-markdown skipHtml` + URL 스킴 화이트리스트 (http/https/mailto/tel) |
| **rehype-raw 차단** | 마크다운 렌더링에 raw HTML 주입 불가 |
| **Slack 토큰 검증** | `xoxp-` / `xoxa-2-` 형식만 허용 (bot 토큰 거부) |
| **이미지 보안** | `referrerPolicy: "no-referrer"` |

---

## 데이터 흐름 다이어그램

### 채팅 (기본 LLM)

```
User → POST /chat/stream → load_company_context()
                              ├→ RAG: knowledge_base.retrieve(query)
                              └→ Drive: fetch drive files (if OAuth)
                           → inject_company_context(messages, context)
                           → AsyncOpenAI.chat.completions.create(stream=True)
                           → iter_text_chunks(chunk, 140)
                           → SSE: data: {"source":"llm","token":"..."}\n\n
                           → SSE: data: [DONE]\n\n
```

### CrewAI 리서치

```
User → POST /chat/stream → should_route_to_crewai() = True
                         → plan_crew(query, config)
                            ├→ DuckDuckGo 검색
                            └→ 에이전트/태스크 동적 생성
                         → SSE: crew_graph (DAG 구조)
                         → execute_crew(plan, config, callback)
                            → 각 태스크 완료 → SSE: crew_progress
                         → iter_text_chunks(report, 140)
                         → SSE: data: [DONE]\n\n
```

### 온보딩 자동화

```
User → "홍길동 개발팀 2026-04-01 hong@co.com"
     → parse_onboarding_profile() = OnboardingProfile
     → Slack 토큰/초대링크 확인
        ├→ 있음 → run_onboarding_workflow()
        └→ 없음 → pending_onboarding_by_session에 저장
                  → "Slack 초대 링크를 입력해주세요" 응답
     → run_onboarding_workflow()
        ├→ Drive 검색 → 관련 문서 링크 수집
        ├→ LLM 요약 생성 → 마크다운 → HTML 변환
        ├→ Gmail 발송 (HTML 이메일)
        └→ Slack 초대 (링크 또는 API)
     → 결과 리포트 스트리밍
```
