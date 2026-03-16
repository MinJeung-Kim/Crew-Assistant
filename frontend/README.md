# Orchestration Frontend

멀티 에이전트 AI 리서치 플랫폼의 프론트엔드 애플리케이션입니다.  
React 19 + TypeScript + Vite 기반의 SPA로, 채팅 UI · CrewAI 실시간 플로우 시각화 · 도구(통합) 관리 기능을 제공합니다.

---

## 기술 스택

| 카테고리 | 라이브러리 | 버전 |
|---------|-----------|------|
| UI 프레임워크 | React | 19.2 |
| 언어 | TypeScript | 5.9 |
| 빌드 도구 | Vite | 7.3 |
| 라우팅 | React Router | 7.13 |
| 그래프 시각화 | @xyflow/react | 12.10 |
| 마크다운 렌더링 | react-markdown + remark-gfm | 10.1 / 4.0 |
| 코드 하이라이팅 | react-syntax-highlighter (Prism) | 16.1 |
| 린트 | ESLint + typescript-eslint | 9.39 |
| 스타일링 | CSS Modules | - |

---

## 디렉토리 구조

```
src/
├── main.tsx                    # 엔트리 포인트 (BrowserRouter + StrictMode)
├── App.tsx                     # 루트 컴포넌트 → ChatUI 렌더링
├── App.css / index.css         # 글로벌 스타일 (DM Sans 폰트, 스크롤바, 색상)
│
├── components/
│   ├── ChatUI.tsx              # 메인 레이아웃 + 라우팅 (채팅 워크스페이스)
│   ├── ChatUI.module.css
│   │
│   ├── chat/
│   │   ├── ChatInput.tsx       # 채팅 입력 (자동 확장 textarea)
│   │   ├── MessageBubble.tsx   # 메시지 버블 (마크다운 + 번역)
│   │   ├── MessageList.tsx     # 메시지 목록 (자동 스크롤)
│   │   └── TypingIndicator.tsx # 타이핑 애니메이션 (3 dots)
│   │
│   ├── flow/
│   │   └── CrewFlowPage.tsx    # CrewAI 그래프 시각화
│   │
│   ├── tools/
│   │   └── ToolsPage.tsx       # 통합 도구 관리 (OAuth, API 키)
│   │
│   ├── layout/
│   │   ├── Header.tsx          # 헤더 (업로드, 다운로드, 아이콘 액션)
│   │   ├── Sidebar.tsx         # 사이드바 네비게이션
│   │   └── ErrorBanner.tsx     # 에러 배너
│   │
│   └── icons/
│       └── index.tsx           # SVG 아이콘 컴포넌트 12종
│
├── hooks/
│   └── useChat.ts              # 채팅 커스텀 훅 (SSE 스트리밍)
│
├── services/
│   ├── chatStream.ts           # SSE 파싱 유틸리티
│   └── knowledgeApi.ts         # 지식 베이스 업로드 API
│
├── types/
│   └── chat.ts                 # 타입 정의 (Message, CrewGraph 등)
│
├── utils/
│   ├── chatExport.ts           # 대화 내보내기 (md, pdf, doc)
│   └── index.ts                # formatTime, generateId
│
└── constants/
    ├── index.ts                # API_BASE, SYSTEM_PROMPT, INITIAL_MESSAGE
    └── navigation.ts           # 네비게이션 섹션/아이템 설정
```

---

## 라우팅

`ChatUI.tsx`에서 React Router로 클라이언트 라우팅을 관리합니다.

| 경로 | 컴포넌트 | 설명 |
|------|---------|------|
| `/chat` | `ChatWorkspace` | 채팅 인터페이스 (기본) |
| `/flow` | `CrewFlowPage` | CrewAI 에이전트/태스크 플로우 |
| `/tools` | `ToolsPage` | Google OAuth · API 키 관리 |
| `/overview` | `PlaceholderPage` | 개요 (준비 중) |
| `/settings` | `PlaceholderPage` | 설정 (준비 중) |
| `/billing` | `PlaceholderPage` | 결제 (준비 중) |
| `/usage` | `PlaceholderPage` | 사용량 (준비 중) |

사이드바 네비게이션은 3개 섹션으로 구분됩니다:
- **(기본)** — Overview
- **Build** — Chat, Flow, Tools
- **Manage** — Settings, Billing, Usage

---

## 주요 컴포넌트

### ChatUI (루트 워크스페이스)

전체 레이아웃을 구성하는 메인 컴포넌트입니다.

**상태 관리:**
- `sessionName` — 세션 이름
- `sidebarOpen` — 사이드바 토글
- `isFullscreen` — 전체화면 모드
- `isUploadingKnowledge` — 지식 베이스 업로드 상태

**주요 기능:**
- 지식 베이스 파일 업로드 (`.txt`, `.md`, `.markdown`, `.pdf`, `.docx`)
- 대화 내보내기 (Markdown, PDF, Word)
- 세션 관리 (생성, 리셋)

---

### ChatInput (채팅 입력)

- 자동 높이 확장 textarea (최대 120px)
- `Enter` — 전송 / `Shift+Enter` — 줄바꿈
- 플레이스홀더: *"예) 2026년 IT 트랜드 조사해서 보고서 형식으로 요약해줘"*
- 전송 버튼 활성 색상: `#ef4444` (빨강) / 비활성: `#f3f4f6`

---

### MessageBubble (메시지 버블)

- **마크다운 렌더링**: react-markdown + Prism 구문 하이라이팅
- **번역 기능**: `POST /translate` API 호출
- **URL 보안**: `http`, `https`, `mailto`, `tel` 스킴만 허용
- 사용자 버블: `#ef4444` (빨강) / 어시스턴트 버블: `#fcfcfd` (밝은 회색)
- Avatar + MessageMeta 서브 컴포넌트 포함

---

### MessageList (메시지 목록)

- `useEffect` + `scrollIntoView({ behavior: 'smooth' })`로 새 메시지 자동 스크롤
- 로딩 시 `TypingIndicator` 표시 (3개 점 펄스 애니메이션, 0s / 0.2s / 0.4s 딜레이)

---

### CrewFlowPage (CrewAI 플로우 시각화)

@xyflow/react를 사용한 에이전트-태스크 그래프 시각화입니다.

**그래프 구조:**
- **에이전트 노드** — 왼쪽 (x: 40), 세로 136px 간격
- **태스크 노드** — 오른쪽 (x: 420), 에이전트와 대응
- **엣지** — `assign` (빨간 화살표: 에이전트→태스크), `depends` (회색 점선: 태스크 간 의존성)
- 줌 범위: 0.45 ~ 1.8

**태스크 상태:**
| 상태 | 라벨 | 스타일 |
|------|------|--------|
| `pending` | 대기 | 기본 |
| `running` | 실행 중 | 파란 테두리, 하늘색 배경 |
| `completed` | 완료 | 초록 테두리, 연초록 배경 |
| `failed` | 실패 | 분홍 테두리, 연분홍 배경 |

---

### ToolsPage (도구 관리)

Google OAuth, API 키, Slack 연동을 관리하는 페이지입니다.

**관리 항목:**
- Google API Key / Slack API Key / Slack Invite Link
- Google OAuth 클라이언트 (JSON 업로드)
- OAuth 토큰 발급 (Installed / Web 방식)
- 스코프 상태 진단 (`gmail.send`, `drive.readonly`, `drive.metadata.readonly`)

**OAuth 플로우 단계 (5단계):**
1. `client_upload` — OAuth 클라이언트 JSON 업로드
2. `auth_url` — 인증 URL 생성
3. `consent` — 사용자 동의
4. `token_exchange` — 토큰 교환
5. `token_save` — 토큰 저장

**온보딩 트리거 형식:** `[이름] [부서] [입사일] [이메일]`

---

### Header (헤더)

| 기능 | 설명 |
|------|------|
| 파일 업로드 | `.txt`, `.md`, `.markdown`, `.pdf`, `.docx` |
| 다운로드 | Markdown / PDF / Word |
| 아이콘 액션 | 새로고침, 중지, 전체화면, 히스토리 |
| 에러 표시 | 빨간 뱃지 + 펄스 애니메이션 |

---

### Sidebar (사이드바)

- 로고: 🪄 Orchestration — GATEWAY DASHBOARD
- 너비: 200px (접힘 시 0px, 0.25s 트랜지션)
- 활성 경로 표시: `NavLink`의 `isActive` + `#ef4444` 빨강 배경
- `navigation.ts`의 `NAV_SECTIONS` 설정 기반 동적 네비게이션

---

## 커스텀 훅

### useChat

채팅 로직 전체를 캡슐화하는 핵심 훅입니다.

```typescript
const {
  messages,         // Message[] — 대화 메시지 배열
  crewGraph,        // CrewGraph | null — 에이전트/태스크 그래프
  crewProgress,     // CrewProgress | null — 실시간 진행 상태
  isLoading,        // boolean — 스트리밍 중 여부
  error,            // string | null — 에러 메시지
  sendMessage,      // (input, sessionId) => Promise<void>
  stopStreaming,     // () => void — 스트리밍 중단
  appendAssistantMessage, // (content, source?) => void
  resetSession,     // () => void — 세션 초기화
  clearError,       // () => void
  updateMessageTranslation, // (id, content, show) => void
} = useChat();
```

**SSE 스트리밍 처리:**
- 엔드포인트: `POST /chat/stream`
- 요청 바디: `{ messages: ChatPayloadMessage[], session_id: string }`
- 이벤트 형식: `data: <JSON>` (SSE 표준)
- JSON 키: `token`, `source`, `crew_graph`, `crew_progress`
- 종료 신호: `[DONE]`

---

## 서비스

### chatStream.ts (SSE 파싱)

```typescript
// SSE 청크 파싱 — 불완전 라인 버퍼링 지원
parseSseChunk(rawChunk: string, pendingBuffer: string)
  → { events: ParsedChatStreamEvent[], remaining: string }

// 타입 가드
isCrewGraph(value)     // CrewGraph 타입 검증
isCrewProgress(value)  // CrewProgress 타입 검증 (task 상태 포함)
```

### knowledgeApi.ts (지식 베이스 업로드)

```typescript
uploadKnowledgeFile(file: File): Promise<KnowledgeUploadResult>
// POST /knowledge/upload — FormData 파일 업로드
// 응답: { chunkCount: number, totalChunks: number }
```

---

## 타입 정의 (types/chat.ts)

### Message
```typescript
interface Message {
  id: string
  role: "assistant" | "user"
  content: string
  timestamp: Date
  source?: string
  translatedContent?: string
  showTranslated?: boolean
}
```

### CrewGraph
```typescript
interface CrewGraph {
  topic: string
  target_year: number
  agents: CrewGraphAgent[]   // { id, role, goal }
  tasks: CrewGraphTask[]     // { id, title, agent_id, depends_on, description?, expected_output? }
}
```

### CrewProgress
```typescript
interface CrewProgress {
  phase: string
  active_task_id: string | null
  active_agent_id: string | null
  detail?: string | null
  updated_at: string
  tasks: CrewProgressTask[]  // { task_id, title, agent_id, status }
}

type CrewTaskStatus = "pending" | "running" | "completed" | "failed"
```

---

## 유틸리티

### chatExport.ts (대화 내보내기)

| 내보내기 형식 | 함수 | 설명 |
|-------------|------|------|
| Markdown | `buildMarkdownExport()` | 세션 이름 + 타임스탬프 + 대화 내역 |
| PDF | `downloadReportAsPdf()` | 새 창 → window.print (Georgia serif, 820px) |
| Word | `downloadReportAsDoc()` | Office XML Blob 다운로드 (Malgun Gothic) |

- `buildCrewReportExport()` — CrewAI 응답만 필터링하여 내보내기
- 세션 이름 정리: 영숫자/한글 외 문자를 `_`로 치환

### utils/index.ts

```typescript
formatTime(date: Date)  // 12시간제 로캘 시간 (en-US)
generateId()            // 7자리 랜덤 base36 문자열
```

---

## 상수

```typescript
// constants/index.ts
API_BASE       = import.meta.env.VITE_API_BASE ?? "http://localhost:8000"
SYSTEM_PROMPT  = "You are a helpful assistant."
INITIAL_MESSAGE = "안녕하세요 😊 무엇을 도와드릴까요?"
```

---

## API 연동

| 엔드포인트 | 메서드 | 용도 |
|-----------|--------|------|
| `/chat/stream` | POST | SSE 채팅 스트리밍 |
| `/translate` | POST | 메시지 번역 |
| `/knowledge/upload` | POST | 지식 베이스 파일 업로드 |
| `/integrations/env` | GET/POST | API 키 조회/저장 |
| `/integrations/google/scope-status` | GET | Google 스코프 상태 |
| `/integrations/google/oauth-client/status` | GET | OAuth 클라이언트 상태 |
| `/integrations/google/oauth-client` | POST | OAuth 클라이언트 JSON 업로드 |
| `/integrations/google/oauth/installed/issue` | POST | Installed 타입 토큰 발급 |
| `/integrations/google/oauth/start` | POST | Web OAuth 플로우 시작 |

---

## 스타일링 패턴

- **CSS Modules**: 모든 컴포넌트에 `*.module.css` 독립 스타일
- **폰트**: DM Sans (본문) / DM Mono (코드, 레이블)
- **색상 체계**:
  - 프라이머리: `#ef4444` (빨강) — 활성 버튼, 사이드바 하이라이트
  - 텍스트: `#1f2937` (다크 그레이) — 본문
  - 배경: `#ffffff` (화이트) — 메인 배경
  - 보조: `#6b7280` (그레이) — 비활성 텍스트
- **스크롤바**: 4px 너비
- **반응형**: max-width 제약, overflow 처리
- **애니메이션**: slideDown (에러 배너), pulse (타이핑/에러), 호버 트랜지션

---

## 아이콘

`components/icons/index.tsx`에서 12종의 SVG 아이콘을 제공합니다.  
모두 `currentColor`를 사용하여 부모 색상을 상속합니다.

| 아이콘 | 컴포넌트 | 크기 |
|--------|---------|------|
| 새로고침 | `IconRefresh` | 14×14 |
| 중지 | `IconStop` | 14×14 |
| 확대 | `IconExpand` | 14×14 |
| 시계 | `IconClock` | 14×14 |
| 전송 | `IconSend` | 16×16 |
| 메뉴 | `IconMenu` | 16×16 |
| 채팅 | `IconChat` | 14×14 |
| 차트 | `IconChart` | 14×14 |
| 레이어 | `IconLayers` | 14×14 |
| 설정 | `IconSettings` | 14×14 |
| 별 | `IconStar` | 14×14 |
| 노드 | `IconNode` | 14×14 |

---

## 개발 가이드

### 실행

```bash
cd frontend
npm install
npm run dev          # Vite 개발 서버 (기본: http://localhost:5173)
```

### 환경 변수

```env
VITE_API_BASE=http://localhost:8000   # 백엔드 API 주소
```

### 빌드

```bash
npm run build        # TypeScript 컴파일 + Vite 프로덕션 빌드 → dist/
npm run preview      # 빌드 결과 미리보기
```

### 린트

```bash
npm run lint         # ESLint 실행
```

### TypeScript 설정

- **앱 코드** (`tsconfig.app.json`): ES2022 타겟, Strict 모드, react-jsx
- **빌드 설정** (`tsconfig.node.json`): ES2023 타겟, vite.config.ts 전용

---

## 보안

- **URL 화이트리스트**: 마크다운 링크에 `http`, `https`, `mailto`, `tel` 스킴만 허용
- **XSS 방지**: react-markdown의 기본 sanitization 적용
- **환경 변수**: `VITE_` 접두사 변수만 클라이언트에 노출 (Vite 기본 정책)
