# Orchestration — Multi-Agent LLM 오케스트레이션 플랫폼

CrewAI 기반 멀티 에이전트 트렌드 리서치, 회사 문서 RAG, 온보딩 자동화, 실시간 스트리밍 채팅을 통합한 풀스택 AI 플랫폼입니다.

---

## 목차

- [주요 기능](#주요-기능)
- [아키텍처](#아키텍처)
- [기술 스택](#기술-스택)
- [프로젝트 구조](#프로젝트-구조)
- [시작하기](#시작하기)
  - [사전 요구사항](#사전-요구사항)
  - [Backend 설치](#backend-설치)
  - [Frontend 설치](#frontend-설치)
  - [환경 변수 설정](#환경-변수-설정)
- [기능 상세](#기능-상세)
  - [CrewAI 멀티 에이전트 오케스트레이션](#crewai-멀티-에이전트-오케스트레이션)
  - [RAG 기반 회사 지식 검색](#rag-기반-회사-지식-검색)
  - [온보딩 자동화](#온보딩-자동화)
  - [Google Drive 컨텍스트](#google-drive-컨텍스트)
  - [Google OAuth 연동](#google-oauth-연동)
- [API 엔드포인트](#api-엔드포인트)
- [Frontend 페이지](#frontend-페이지)

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| **실시간 스트리밍 채팅** | SSE 기반 실시간 토큰 스트리밍 + CrewAI 진행 상황 표시 |
| **CrewAI 멀티 에이전트** | 쿼리 분석 → 동적 에이전트 구성 → 웹 리서치 → 보고서 생성 |
| **회사 RAG** | PDF/DOCX/TXT/MD/CSV/JSON 업로드 → 청킹 → 임베딩 → 하이브리드 검색 |
| **Google Drive 컨텍스트** | OAuth 인증 후 Drive 문서 자동 검색 + 채팅 컨텍스트 주입 |
| **온보딩 자동화** | 프로필 입력 → Gmail 발송 + Slack 초대 + Drive 문서 연동 |
| **번역** | 마크다운 포맷 보존 다국어 번역 |
| **CrewAI 플로우 시각화** | 에이전트/태스크 DAG 그래프 실시간 상태 표시 |
| **보고서 내보내기** | Markdown/PDF/Word 형식 다운로드 |

---

## 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (React 19 + TypeScript + Vite)                │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────────┐  │
│  │ Chat UI  │  │ CrewFlow  │  │ Tools (Integrations) │  │
│  └────┬─────┘  └─────┬─────┘  └──────────┬───────────┘  │
│       │              │                    │              │
│       └──────────────┼────────────────────┘              │
│                      │ SSE / REST                        │
└──────────────────────┼──────────────────────────────────┘
                       │
┌──────────────────────┼──────────────────────────────────┐
│  Backend (FastAPI + Uvicorn)                             │
│       ┌──────────────┴───────────────┐                   │
│       │         Router               │                   │
│       │  (Onboarding / CrewAI / LLM) │                   │
│       └──┬──────────┬───────────┬────┘                   │
│          │          │           │                         │
│  ┌───────┴───┐ ┌────┴────┐ ┌───┴──────────┐             │
│  │  CrewAI   │ │   RAG   │ │  Onboarding  │             │
│  │ Planning  │ │ Hybrid  │ │  Gmail+Slack  │             │
│  │ Routing   │ │ Search  │ │  +Drive       │             │
│  │ Execution │ │         │ │              │              │
│  └───────────┘ └────┬────┘ └──────────────┘              │
│                     │                                    │
│         ┌───────────┼───────────┐                        │
│         │           │           │                        │
│    ┌────┴────┐ ┌────┴────┐ ┌───┴──────┐                 │
│    │ OpenAI  │ │ Google  │ │ DuckDuck │                  │
│    │   LLM   │ │ Drive   │ │   Go     │                  │
│    │Embedding│ │ Gmail   │ │  Search  │                  │
│    └─────────┘ └─────────┘ └──────────┘                  │
└──────────────────────────────────────────────────────────┘
```

---

## 기술 스택

### Backend

| 패키지 | 버전 | 용도 |
|---------|------|------|
| FastAPI | ≥0.115 | REST API + OpenAPI 자동 문서화 |
| Uvicorn | ≥0.30 | ASGI 서버 |
| OpenAI | ≥1.50 | LLM 호출 (스트리밍 completions, embeddings) |
| CrewAI | ≥0.175 | 멀티 에이전트 오케스트레이션 |
| LiteLLM | ≥1.74 | OpenAI 호환 모델 프록시 |
| ddgs | ≥9.6 | DuckDuckGo 웹 검색 (트렌드 리서치) |
| pypdf | ≥5.4 | PDF 텍스트 추출 |
| python-docx | ≥1.1 | DOCX 텍스트 추출 |
| httpx | ≥0.27 | 비동기 HTTP (OAuth, Drive API) |
| google-auth | ≥2.35 | Google OAuth 2.0 인증 |
| Pydantic | ≥2.5 | 데이터 검증 + 설정 관리 |
| Markdown | ≥3.7 | 온보딩 이메일 HTML 변환 |

### Frontend

| 패키지 | 버전 | 용도 |
|---------|------|------|
| React | ≥19.2 | UI 프레임워크 |
| TypeScript | ~5.9 | 타입 안전성 |
| Vite | ≥7.3 | 빌드 도구 |
| React Router | ≥7.13 | SPA 라우팅 |
| @xyflow/react | ≥12.10 | CrewAI 플로우 그래프 시각화 |
| react-markdown | ≥10.1 | 마크다운 렌더링 (remark-gfm) |
| react-syntax-highlighter | ≥16.1 | 코드 블록 하이라이팅 |

---

## 프로젝트 구조

```
orchestration/
├── backend/
│   ├── main.py                    # FastAPI 앱 + 전체 API 엔드포인트
│   ├── config.py                  # Pydantic Settings 환경 설정
│   ├── knowledge_base.py          # RAG 지식 베이스 (청킹, 임베딩, 검색)
│   ├── onboarding_workflow.py     # 온보딩 자동화 (프로필 파싱, Gmail, Slack)
│   ├── requirements.txt           # Python 의존성
│   ├── crew/                      # CrewAI 멀티 에이전트 모듈
│   │   ├── routing.py             # 쿼리 → CrewAI 라우팅 판단
│   │   ├── planning.py            # 동적 에이전트/태스크 생성
│   │   ├── execution.py           # Crew 실행 + 스트리밍 진행 콜백
│   │   ├── search.py              # DuckDuckGo 웹 검색
│   │   ├── formatting.py          # 보고서 마크다운 포맷팅
│   │   ├── models.py              # 데이터 모델 (에이전트, 태스크 등)
│   │   ├── constants.py           # 키워드 상수
│   │   └── serialization.py       # 직렬화 유틸
│   ├── services/                  # 비즈니스 서비스 레이어
│   │   ├── chat_service.py        # LLM 호출, 번역, CrewAI 리포트 위임
│   │   ├── drive_context.py       # Google Drive 파일 검색 + 컨텍스트 추출
│   │   ├── google_oauth.py        # OAuth 클라이언트 설정, 토큰 관리
│   │   └── streaming.py           # SSE 페이로드 포맷팅 + 청크 분할
│   ├── data/
│   │   ├── knowledge/             # RAG 문서 저장소
│   │   └── oauth/                 # Google OAuth 토큰 저장소
│   └── tests/                     # 유닛 테스트
├── frontend/
│   ├── src/
│   │   ├── App.tsx                # 앱 라우터 + 레이아웃
│   │   ├── components/
│   │   │   ├── ChatUI.tsx         # 채팅 워크스페이스 메인
│   │   │   ├── chat/              # 메시지 버블, 입력, 리스트, 타이핑 인디케이터
│   │   │   ├── flow/              # CrewAI 플로우 시각화 페이지
│   │   │   ├── tools/             # 통합 설정 페이지 (Slack, Google OAuth)
│   │   │   ├── layout/            # Header, Sidebar, ErrorBanner
│   │   │   └── icons/             # SVG 아이콘 컴포넌트
│   │   ├── hooks/
│   │   │   └── useChat.ts         # 채팅 상태 관리 + SSE 구독 훅
│   │   ├── services/
│   │   │   ├── chatStream.ts      # SSE 스트림 파싱
│   │   │   └── knowledgeApi.ts    # 지식 베이스 업로드 API
│   │   ├── types/
│   │   │   └── chat.ts            # 채팅 타입 정의
│   │   ├── utils/
│   │   │   ├── chatExport.ts      # 보고서 내보내기 (MD/PDF/Word)
│   │   │   └── index.ts           # 공통 유틸
│   │   └── constants/             # 상수 (네비게이션, 설정)
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
└── README.md                      # ← 이 파일
```

---

## 시작하기

### 사전 요구사항

- **Python** 3.11+
- **Node.js** 18+
- **OpenAI API Key** (또는 호환 LLM 엔드포인트)

### Backend 설치

```bash
cd backend

# 가상 환경 생성 및 활성화
python -m venv ../.venv
source ../.venv/Scripts/activate   # Windows
# source ../.venv/bin/activate     # macOS/Linux

# 의존성 설치
pip install -r requirements.txt

# .env 파일 생성 (아래 환경 변수 섹션 참고)
cp .env.example .env

# 서버 실행
uvicorn main:app --reload
```

서버가 `http://localhost:8000` 에서 실행됩니다. API 문서는 `http://localhost:8000/docs`에서 확인 가능합니다.

### Frontend 설치

```bash
cd frontend

# 의존성 설치
npm install

# 개발 서버 실행
npm run dev
```

프론트엔드가 `http://localhost:3000` 에서 실행됩니다.

### 환경 변수 설정

Backend `.env` 파일에 다음 환경 변수를 설정합니다:

```env
# ─── LLM 설정 (필수) ───────────────────────────────
LLM_PROVIDER=openai
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4-turbo

# ─── CrewAI 설정 ───────────────────────────────────
CREWAI_ENABLED=true
CREWAI_MODEL=                         # 비어있으면 openai/<LLM_MODEL> 사용
CREWAI_WEB_SEARCH_RESULTS=6           # DuckDuckGo 검색 결과 수 (1~12)

# ─── RAG 설정 ──────────────────────────────────────
RAG_ENABLED=true
RAG_STORAGE_PATH=./data/knowledge
RAG_EMBEDDING_MODEL=text-embedding-3-small
RAG_TOP_K=4                           # 검색 결과 수 (1~12)
RAG_MAX_CHUNK_CHARS=900               # 청크 크기 (300~3000)
RAG_CHUNK_OVERLAP=120                 # 청크 겹침 (0~500)
RAG_MAX_UPLOAD_MB=20                  # 최대 업로드 크기 (1~200MB)

# ─── Google Drive 컨텍스트 ─────────────────────────
GOOGLE_DRIVE_CONTEXT_ENABLED=true
GOOGLE_DRIVE_CONTEXT_RESULTS=4
GOOGLE_DRIVE_CONTEXT_MAX_CHARS=1400
GOOGLE_DRIVE_CONTEXT_MAX_FILE_BYTES=4000000

# ─── 통합 서비스 키 (런타임 API로도 설정 가능) ─────
GOOGLE_API_KEY=
SLACK_API_KEY=                        # 관리자 토큰 xoxp-/xoxa-2-
SLACK_INVITE_LINK=                    # Slack 공유 초대 URL
SLACK_TEAM_ID=

# ─── Google OAuth ──────────────────────────────────
GOOGLE_OAUTH_TOKEN_PATH=./data/oauth/token.json
GOOGLE_OAUTH_INSTALLED_PORT=8080

# ─── 서버 ─────────────────────────────────────────
APP_HOST=0.0.0.0
APP_PORT=8000
APP_ENV=development
CORS_ORIGINS=http://localhost:3000

# ─── 온보딩 ───────────────────────────────────────
ONBOARDING_DRIVE_FILE_LIMIT=8
```

---

## 기능 상세

### CrewAI 멀티 에이전트 오케스트레이션

사용자 쿼리에 트렌드/리서치/보고서 관련 키워드가 감지되면 자동으로 CrewAI 멀티 에이전트 파이프라인이 작동합니다.

**동적 에이전트 구성:**
- **Researcher** + **Trend Analyst** — 항상 포함 (핵심 리서치)
- **Market Analyst** — 시장/도입 관련 키워드 시 추가
- **Risk Analyst** — 정책/규제 관련 키워드 시 추가
- **Strategy Planner** — 로드맵/실행 관련 키워드 시 추가
- **Report Writer** — 최종 마크다운 보고서 작성

**실행 흐름:**

```
쿼리 분석 → 에이전트 동적 구성 → DuckDuckGo 웹 검색
    → 리서치 → 트렌드 분석 → [시장분석] → [정책분석] → [전략]
    → 최종 보고서 생성 (마크다운)
```

**예시 트리거 쿼리:**
```
2026년 IT 트렌드 조사해서 보고서 형식으로 요약해줘
```

### RAG 기반 회사 지식 검색

회사 문서를 업로드하면 자동으로 청킹 → 임베딩 → 인덱싱되어 채팅 컨텍스트에 주입됩니다.

**지원 파일 형식:** PDF, DOCX, TXT, MD, CSV, JSON

**검색 방식:** 하이브리드 (벡터 유사도 + 어휘 매칭)
- 임베딩이 있으면 코사인 유사도 기반 벡터 검색
- 없으면 키워드 기반 어휘 스코어링으로 폴백

### 온보딩 자동화

채팅으로 신규 직원 정보를 입력하면 자동 온보딩 프로세스가 실행됩니다.

**입력 형식:**
```
홍길동 개발팀 2026-04-01 gildong@company.com
```

**자동화 단계:**
1. 프로필 파싱 및 검증
2. Slack 초대 (공유 초대 링크 또는 관리자 토큰)
3. Gmail 온보딩 이메일 발송 (HTML 포맷, 체크리스트 포함)
4. Google Drive 관련 문서 검색 및 링크 첨부
5. 결과 요약 리포트

### Google Drive 컨텍스트

OAuth 인증 후 사용자의 Google Drive 문서가 채팅 컨텍스트에 자동 포함됩니다.

- 쿼리 키워드 기반 Drive 파일 자동 검색
- Google Docs/Sheets/Slides → 텍스트 자동 변환
- PDF/DOCX/TXT/MD/CSV 직접 다운로드
- 최대 파일 크기 제한 (기본 4MB)

### Google OAuth 연동

두 가지 OAuth 플로우를 지원합니다:

**1. Web App Flow (기본)**
- OAuth 클라이언트 JSON 업로드 → 팝업 인증 → 토큰 발급

**2. Installed App Flow (데스크톱)**
- Installed 클라이언트 JSON 업로드 → 로컬 서버(8080) → 브라우저 인증 → token.json 자동 저장 + 리프레시

**요청 스코프:**
- `openid`, `userinfo.email`
- `drive.readonly` (Drive 컨텍스트)
- `gmail.send` (온보딩 이메일)

---

## API 엔드포인트

### 채팅

| Method | Endpoint | 설명 |
|--------|----------|------|
| `POST` | `/chat` | 비스트리밍 채팅 (CrewAI/RAG/온보딩/LLM 라우팅) |
| `POST` | `/chat/stream` | SSE 스트리밍 채팅 (실시간 진행 상황) |
| `POST` | `/translate` | 텍스트 번역 (마크다운 포맷 보존 옵션) |

### 지식 베이스 (RAG)

| Method | Endpoint | 설명 |
|--------|----------|------|
| `GET` | `/knowledge/status` | RAG 상태 조회 (청크 수, 문서 목록) |
| `POST` | `/knowledge/upload` | 회사 문서 업로드 (PDF/DOCX/TXT/MD/CSV/JSON) |

### 통합 서비스

| Method | Endpoint | 설명 |
|--------|----------|------|
| `GET` | `/integrations/env` | 통합 키 상태 조회 (마스킹된 값) |
| `POST` | `/integrations/env` | 통합 키 업데이트 |

### Google OAuth

| Method | Endpoint | 설명 |
|--------|----------|------|
| `POST` | `/integrations/google/oauth-client` | OAuth 클라이언트 JSON 업로드 |
| `DELETE` | `/integrations/google/oauth-client` | OAuth 클라이언트 설정 초기화 |
| `GET` | `/integrations/google/oauth/start` | OAuth 인증 URL 생성 |
| `GET` | `/integrations/google/oauth/callback` | OAuth 콜백 처리 |
| `POST` | `/integrations/google/oauth/installed/issue` | Installed 플로우 토큰 발급 |
| `GET` | `/integrations/google/scope-status` | OAuth 스코프 상태 확인 |

### 헬스체크

| Method | Endpoint | 설명 |
|--------|----------|------|
| `GET` | `/health` | 서버 상태 확인 |

---

## Frontend 페이지

| 경로 | 컴포넌트 | 설명 |
|------|----------|------|
| `/chat` | ChatUI | 메인 채팅 인터페이스 (스트리밍, 번역, 내보내기) |
| `/flow` | CrewFlowPage | CrewAI 에이전트/태스크 DAG 실시간 시각화 |
| `/tools` | ToolsPage | Slack/Google 통합 설정 + OAuth 관리 |

**UI 주요 기능:**
- 실시간 SSE 토큰 스트리밍 + CrewAI 진행 상황 표시
- 마크다운 렌더링 + 코드 하이라이팅
- 보고서 다운로드 (Markdown / PDF / Word)
- 인라인 번역 토글
- 회사 문서 드래그앤드롭 업로드
- 전체 화면 모드

---

## 테스트

### Backend 유닛 테스트

```bash
cd backend
../.venv/Scripts/python.exe -m unittest discover -s tests -v
```

### Frontend 빌드 검증

```bash
cd frontend
npm run build
```

---

## 라이선스

Private Repository
