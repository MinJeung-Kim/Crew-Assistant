# Frontend 개발 가이드

## 개요

React 19 + TypeScript + Vite 기반 SPA(Single Page Application)로, 실시간 SSE 스트리밍 채팅, CrewAI 플로우 시각화, 통합 설정 관리 UI를 제공합니다.

---

## 기술 스택

| 패키지 | 버전 | 용도 |
|---------|------|------|
| React | 19.2+ | UI 프레임워크 |
| TypeScript | 5.9+ | 타입 안전성 |
| Vite | 7.3+ | 빌드 + HMR |
| React Router | 7.13+ | SPA 라우팅 |
| @xyflow/react | 12.10+ | DAG 그래프 시각화 |
| react-markdown | 10.1+ | 마크다운 렌더링 |
| react-syntax-highlighter | 16.1+ | 코드 블록 하이라이팅 |
| remark-gfm | 4.0+ | GFM (테이블, 체크리스트 등) |

---

## 디렉토리 구조

```
frontend/src/
├── App.tsx                        # 앱 라우터 + 레이아웃
├── main.tsx                       # 엔트리 포인트
├── App.css / index.css            # 전역 스타일
├── components/
│   ├── ChatUI.tsx                 # 채팅 워크스페이스 메인
│   ├── ChatUI.module.css
│   ├── chat/
│   │   ├── ChatInput.tsx          # 메시지 입력 컴포넌트
│   │   ├── MessageBubble.tsx      # 메시지 버블 (마크다운 렌더링)
│   │   ├── MessageList.tsx        # 메시지 리스트 (자동 스크롤)
│   │   └── TypingIndicator.tsx    # 타이핑 인디케이터
│   ├── flow/
│   │   └── CrewFlowPage.tsx       # CrewAI DAG 시각화
│   ├── tools/
│   │   └── ToolsPage.tsx          # 통합 설정 관리
│   ├── layout/
│   │   ├── Header.tsx             # 헤더 (액션 버튼)
│   │   ├── Sidebar.tsx            # 사이드바 네비게이션
│   │   └── ErrorBanner.tsx        # 에러 배너
│   └── icons/
│       └── index.tsx              # SVG 아이콘 컴포넌트
├── hooks/
│   └── useChat.ts                 # 채팅 상태 관리 훅
├── services/
│   ├── chatStream.ts              # SSE 스트림 파싱
│   └── knowledgeApi.ts            # 지식 베이스 API
├── types/
│   └── chat.ts                    # TypeScript 타입 정의
├── utils/
│   ├── chatExport.ts              # 보고서 내보내기
│   └── index.ts                   # 공통 유틸리티
└── constants/
    ├── index.ts                   # 앱 상수
    └── navigation.ts              # 네비게이션 설정
```

---

## 라우팅

### App.tsx

```
/             → redirect to /chat
/chat         → ChatUI (채팅)
/flow         → CrewFlowPage (CrewAI 시각화)
/tools        → ToolsPage (통합 설정)
/overview     → 개요 (placeholder)
/settings     → 설정 (placeholder)
/billing      → 결제 (placeholder)
/usage        → 사용량 (placeholder)
```

### 레이아웃

```
┌──────────────────────────────────────┐
│  Sidebar  │       Header             │
│           │──────────────────────────│
│  네비게이션 │                          │
│  트리       │    Page Content          │
│           │    (라우터 영역)           │
│           │                          │
│           │                          │
└───────────┴──────────────────────────┘
```

### 네비게이션 구조 (navigation.ts)

```
섹션 1 (이름 없음):
  - Overview  →  /overview

섹션 2 (Build):
  - Chat      →  /chat
  - Flow      →  /flow
  - Tools     →  /tools

섹션 3 (Manage):
  - Settings  →  /settings
  - Billing   →  /billing
  - Usage     →  /usage
```

---

## 핵심 컴포넌트

### ChatUI.tsx

채팅 워크스페이스의 메인 컴포넌트. `useChat` 훅으로 상태를 관리합니다.

**기능:**
- 메시지 표시 + 입력
- SSE 스트리밍 수신
- CrewAI 진행 상황 표시
- 보고서 내보내기 (Markdown, PDF, Word)
- 지식 베이스 업로드
- 전체 화면 모드
- 대화 중지 (AbortController)

### MessageBubble.tsx

개별 메시지 렌더링. 마크다운 + 번역 기능을 포함합니다.

**마크다운 렌더링:**
- `react-markdown` + `remark-gfm` (테이블, 취소선, 체크리스트)
- `react-syntax-highlighter` (코드 블록 하이라이팅)
- `skipHtml: true` (XSS 방지)

**보안:**
- URL 스킴 화이트리스트: `http`, `https`, `mailto`, `tel`
- 이미지 `referrerPolicy: "no-referrer"`
- raw HTML 주입 차단 (`rehype-raw` 미사용)

**번역 기능:**
- 번역 버튼 클릭 → `POST /translate` 호출
- `translatedContent` 필드에 결과 저장
- `showTranslated` 토글로 원문/번역 전환

### ChatInput.tsx

메시지 입력 컴포넌트.

**기능:**
- 자동 높이 조절 textarea
- Enter 키 전송 (Shift+Enter: 줄바꿈)
- 스트리밍 중 비활성화

### MessageList.tsx

메시지 리스트 + 자동 스크롤.

**기능:**
- 새 메시지 추가 시 smooth 스크롤
- `TypingIndicator` 표시 (스트리밍 시작 시)

### CrewFlowPage.tsx

`@xyflow/react`를 사용한 CrewAI 태스크 DAG 시각화.

**노드 스타일:**
```
pending    → 회색 (gray)
running    → 파란색 (blue) + 애니메이션
completed  → 초록색 (green)
failed     → 분홍색 (pink/red)
```

**레이아웃:**
- 에이전트 → 담당 태스크 매핑
- 태스크 간 `depends_on` 기반 엣지 연결
- 실시간 상태 업데이트 (SSE `crew_progress` 이벤트)

### ToolsPage.tsx

통합 설정 관리 UI.

**섹션:**
1. **Slack 설정** — 초대 링크 / 관리자 토큰 입력
2. **Google OAuth** — 클라이언트 JSON 업로드 → 인증 → 스코프 확인
3. **5단계 시각화** — 업로드 → 설정 → 인증 → 토큰 → 완료

### Header.tsx

상단 헤더 액션 버튼.

| 버튼 | 기능 |
|------|------|
| 새로고침 | 대화 초기화 |
| 정지 | 스트리밍 중단 (AbortController) |
| 확대 | 전체 화면 토글 |
| 히스토리 | 대화 기록 모달 |
| 다운로드 | 보고서 내보내기 (드롭다운: MD/PDF/Word) |
| 업로드 | 지식 베이스 문서 업로드 |

### Sidebar.tsx

좌측 네비게이션 트리.

### ErrorBanner.tsx

상단 에러/경고 배너 (닫기 가능).

---

## 상태 관리

### useChat Hook

채팅의 모든 상태를 관리하는 커스텀 훅입니다.

```typescript
const {
  messages,        // Message[]        - 대화 메시지
  isStreaming,     // boolean          - 스트리밍 중 여부
  error,           // string | null    - 에러 메시지
  crewGraph,       // CrewGraph | null - CrewAI DAG 그래프
  crewProgress,    // CrewProgress | null - 태스크 진행 상황
  sendMessage,     // (content: string) => void
  stopStreaming,   // () => void
  clearMessages,   // () => void
  translateMessage, // (messageId: string) => void
} = useChat();
```

**SSE 구독 흐름:**

```
sendMessage(content)
    → POST /chat/stream (ReadableStream)
    → reader.read() 루프
        → parseSseChunk(rawChunk, pendingBuffer)
            → token → messages에 누적
            → crewGraph → crewGraph 상태 설정
            → crewProgress → crewProgress 상태 갱신
            → done → 스트리밍 종료
    → AbortController로 중단 가능
```

---

## SSE 스트림 파싱 (chatStream.ts)

### ParsedChatStreamEvent

```typescript
interface ParsedChatStreamEvent {
  token: string;              // 텍스트 청크
  source?: string;            // 응답 소스
  crewGraph?: CrewGraph;      // DAG 그래프 (최초 1회)
  crewProgress?: CrewProgress; // 태스크 진행 상황
  done: boolean;              // 완료 여부
}
```

### 파싱 알고리즘

```typescript
function parseSseChunk(rawChunk: string, pendingBuffer: string) {
  // 1. 이전 미완성 버퍼 + 새 청크 합치기
  // 2. 줄 단위 분할
  // 3. 마지막 줄은 미완성일 수 있으므로 다음 버퍼로
  // 4. "data: " prefix가 있는 줄만 처리
  // 5. "[DONE]" → done=true
  // 6. JSON.parse → CrewGraph/CrewProgress 타입 가드
  return { events, pendingBuffer };
}
```

### 타입 가드

```typescript
isCrewGraph(value)     // topic, target_year, agents[], tasks[] 존재 확인
isCrewProgress(value)  // phase, active_task_id, tasks[] 검증
isCrewTaskStatus(value) // "pending" | "running" | "completed" | "failed"
```

---

## 타입 시스템 (types/chat.ts)

### Message

```typescript
interface Message {
  id: string;
  role: "assistant" | "user";
  content: string;
  timestamp: Date;
  source?: string;                // "llm" | "crewai" | "onboarding"
  translatedContent?: string;     // 번역된 내용
  showTranslated?: boolean;       // 번역 표시 여부
}
```

### CrewGraph

```typescript
interface CrewGraph {
  topic: string;
  target_year: number;
  agents: CrewGraphAgent[];
  tasks: CrewGraphTask[];
}
```

### CrewProgress

```typescript
interface CrewProgress {
  phase: string;
  active_task_id: string | null;
  active_agent_id: string | null;
  detail?: string | null;
  updated_at: string;
  tasks: CrewProgressTask[];
}

type CrewTaskStatus = "pending" | "running" | "completed" | "failed";
```

---

## 유틸리티

### chatExport.ts — 보고서 내보내기

| 함수 | 형식 | 설명 |
|------|------|------|
| Markdown 내보내기 | `.md` | 세션 헤더 + 메시지별 포맷 |
| PDF 내보내기 | `.pdf` | 마크다운 → HTML 변환 → 인쇄 다이얼로그 |
| Word 내보내기 | `.docx` | Office XML HTML (Malgun Gothic 폰트, 한국어 지원) |
| JSON 내보내기 | `.json` | 전체 세션 상태 (메시지 + CrewAI 데이터) |

### knowledgeApi.ts — 지식 베이스 API

| 함수 | 설명 |
|------|------|
| `uploadKnowledge(file)` | `POST /knowledge/upload` (FormData) |
| `getKnowledgeStatus()` | `GET /knowledge/status` |

---

## 스타일링

### CSS Modules

모든 컴포넌트는 `*.module.css` 파일로 스코프된 스타일을 사용합니다.

| 파일 | 컴포넌트 |
|------|----------|
| `ChatUI.module.css` | 채팅 레이아웃 |
| `ChatInput.module.css` | 입력 영역 |
| `MessageBubble.module.css` | 메시지 버블 |
| `MessageList.module.css` | 메시지 리스트 |
| `TypingIndicator.module.css` | 타이핑 애니메이션 |
| `CrewFlowPage.module.css` | DAG 시각화 |
| `ToolsPage.module.css` | 통합 설정 |
| `Header.module.css` | 헤더 |
| `Sidebar.module.css` | 사이드바 |
| `ErrorBanner.module.css` | 에러 배너 |

### CrewAI 상태 색상

```css
pending    → #9ca3af (gray-400)
running    → #3b82f6 (blue-500) + pulse animation
completed  → #22c55e (green-500)
failed     → #ef4444 (red-500)
```

---

## 보안

| 영역 | 구현 |
|------|------|
| XSS 방지 | `react-markdown skipHtml` — raw HTML 렌더링 차단 |
| URL 필터링 | `http`, `https`, `mailto`, `tel` 스킴만 허용 |
| 이미지 보안 | `referrerPolicy="no-referrer"` |
| rehype-raw 차단 | 마크다운에 raw HTML 삽입 불가 |
| HTML 이스케이핑 | `<br>` 보존하며 나머지 이스케이프 |

---

## 빌드 및 개발

### 개발 서버

```bash
cd frontend
npm install
npm run dev         # Vite HMR 개발 서버 (localhost:3000)
```

### 프로덕션 빌드

```bash
npm run build       # TypeScript 빌드 + Vite 프로덕션 번들
npm run preview     # 빌드 결과 미리보기
```

### Lint

```bash
npm run lint        # ESLint 검사
```

### Vite 설정 (vite.config.ts)

- React 플러그인 (`@vitejs/plugin-react`)
- 개발 서버 포트: 3000 (proxy 설정에 따라)
