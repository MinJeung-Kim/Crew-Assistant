# 개발 가이드

## 개발 환경 설정

### 사전 요구사항

- **Python** 3.11+
- **Node.js** 18+
- **Git**
- **OpenAI API Key** (또는 호환 LLM 엔드포인트)

### 초기 설정

```bash
# 1. 저장소 클론
git clone <repository-url>
cd orchestration

# 2. Python 가상 환경
python -m venv .venv
source .venv/Scripts/activate   # Windows
# source .venv/bin/activate     # macOS/Linux

# 3. Backend 의존성
cd backend
pip install -r requirements.txt

# 4. Frontend 의존성
cd ../frontend
npm install
```

### 환경 변수 설정

```bash
cd backend
cp .env.example .env
# .env 파일 편집 — LLM_API_KEY 등 필수 값 설정
```

필수 환경 변수:
- `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`

전체 환경 변수 목록은 `doc/architecture.md`의 설정 섹션 또는 `backend/config.py`를 참고하세요.

---

## 서버 실행

### Backend (FastAPI)

```bash
cd backend
uvicorn main:app --reload
```

- URL: `http://localhost:8000`
- API 문서: `http://localhost:8000/docs`
- `--reload`: 코드 변경 시 자동 재시작

### Frontend (Vite)

```bash
cd frontend
npm run dev
```

- URL: `http://localhost:3000`
- Vite HMR (Hot Module Replacement) 활성화

---

## 프로젝트 구조 규칙

### Backend

```
backend/
├── main.py                  # API 엔드포인트 + 앱 설정
├── config.py                # Pydantic Settings (환경 변수)
├── knowledge_base.py        # RAG 도메인 로직
├── onboarding_workflow.py   # 온보딩 도메인 로직
├── crew/                    # CrewAI 모듈 (자체 완결)
│   ├── routing.py           # 진입점: should_route_to_crewai()
│   ├── planning.py          # 계획 수립
│   ├── execution.py         # 실행
│   └── ...
├── services/                # 서비스 레이어
│   ├── chat_service.py      # LLM 호출 + 컨텍스트 로딩
│   ├── drive_context.py     # Google Drive 연동
│   ├── google_oauth.py      # OAuth 토큰 관리
│   └── streaming.py         # SSE 포맷팅
├── data/                    # 런타임 데이터 (gitignore 대상)
└── tests/                   # 유닛 테스트
```

**원칙:**
- `main.py`: API 엔드포인트 + Pydantic 모델 + 라우팅 로직만
- `services/`: 외부 서비스 연동 + 비즈니스 서비스
- `crew/`: CrewAI 관련 코드 모듈 (자체 완결적)
- 도메인 로직(`knowledge_base.py`, `onboarding_workflow.py`)은 최상위

### Frontend

```
frontend/src/
├── components/             # UI 컴포넌트
│   ├── chat/               # 채팅 관련
│   ├── flow/               # CrewAI 시각화
│   ├── tools/              # 통합 설정
│   ├── layout/             # 공통 레이아웃
│   └── icons/              # 아이콘
├── hooks/                  # 커스텀 훅
├── services/               # API 호출 서비스
├── types/                  # TypeScript 타입
├── utils/                  # 유틸리티 함수
└── constants/              # 상수
```

**원칙:**
- 컴포넌트당 CSS Module 파일 1:1 매핑
- 상태 관리는 커스텀 훅으로 분리
- API 호출은 `services/`에 집중
- 타입은 `types/`에 모아서 관리

---

## 테스트

### Backend 유닛 테스트

```bash
cd backend
../.venv/Scripts/python.exe -m unittest discover -s tests -v
```

**테스트 파일:**

| 파일 | 대상 |
|------|------|
| `test_chat_service.py` | 채팅 서비스 (LLM 호출, 컨텍스트 주입) |
| `test_drive_context_service.py` | Drive 컨텍스트 서비스 |
| `test_google_oauth_service.py` | OAuth 토큰 관리 |
| `test_knowledge_base_upload.py` | RAG 문서 업로드 + 인제스트 |
| `test_onboarding_email_html.py` | 온보딩 이메일 HTML 렌더링 |
| `test_onboarding_slack_token.py` | Slack 토큰 검증 |
| `test_streaming_service.py` | SSE 포맷팅 + 청크 분할 |

### Frontend 빌드 검증

```bash
cd frontend
npm run build    # TypeScript 컴파일 + Vite 빌드
npm run lint     # ESLint 검사
```

---

## 코드 컨벤션

### Python (Backend)

- **타입 힌트**: 모든 함수에 반환 타입 + 매개변수 타입
- **Pydantic**: 입력 검증에 `BaseModel` + `Field` + `field_validator`
- **비동기**: FastAPI 엔드포인트는 `async def`, CPU-bound 작업은 `asyncio.to_thread()`
- **Dataclass**: 도메인 모델은 `@dataclass(frozen=True)` (불변)
- **에러 처리**: `HTTPException`으로 적절한 상태 코드 반환

### TypeScript (Frontend)

- **인터페이스**: 모든 props와 데이터 구조에 `interface` 정의
- **타입 가드**: SSE 파싱 시 런타임 타입 검증
- **CSS Modules**: 스타일은 `*.module.css`로 스코프
- **훅 패턴**: 복잡한 상태 로직은 커스텀 훅으로 분리

---

## 데이터 저장소

### 런타임 데이터

```
backend/data/
├── knowledge/
│   └── company_knowledge.json    # RAG 인덱스 (JSON)
└── oauth/
    └── token.json                # Google OAuth 토큰
```

이 디렉토리의 파일들은 런타임에 생성/갱신되며 `.gitignore`에 포함되어야 합니다.

### 앱 상태 (인메모리)

| 상태 | 위치 | 영속성 |
|------|------|--------|
| LLM 클라이언트 | `app.state.llm_client` | 서버 수명 |
| RAG 인덱스 | `app.state.knowledge_base` | 서버 수명 + JSON 파일 |
| 통합 키 | `app.state.integration_secrets` | 서버 수명 |
| OAuth 클라이언트 | `app.state.google_oauth_client` | 서버 수명 |
| OAuth state | `app.state.google_oauth_states` | 10분 TTL |
| 온보딩 대기 세션 | `app.state.pending_onboarding_by_session` | 10분 TTL |

---

## 디버깅

### Backend 로그

서버 시작 시 초기화 상태를 출력합니다:

```
✅ LLM client ready  model=gpt-4-turbo  url=https://api.openai.com/v1
✅ Knowledge base ready path=./data/knowledge
✅ Integration secret store ready
✅ Google OAuth token store loaded token=ya29...abc
```

### API 문서 활용

`http://localhost:8000/docs`에서 Swagger UI를 통해:
- 모든 엔드포인트 확인
- 요청/응답 스키마 확인
- 직접 API 호출 테스트

### SSE 디버깅

브라우저 DevTools > Network 탭에서 `/chat/stream` 요청의 EventStream 탭으로 실시간 이벤트를 확인할 수 있습니다.

---

## 의존성 관리

### Backend 의존성 추가

```bash
cd backend
pip install <package>
pip freeze > requirements.txt  # 또는 직접 requirements.txt 편집
```

### Frontend 의존성 추가

```bash
cd frontend
npm install <package>
npm install -D <dev-package>
```

---

## 주요 문서 참조

| 문서 | 내용 |
|------|------|
| [architecture.md](architecture.md) | 시스템 아키텍처, 레이어 구조, 상태 관리 |
| [api-reference.md](api-reference.md) | 전체 API 엔드포인트 상세 |
| [crewai-orchestration.md](crewai-orchestration.md) | CrewAI 멀티 에이전트 시스템 |
| [rag-knowledge-base.md](rag-knowledge-base.md) | RAG 지식 베이스 |
| [onboarding-workflow.md](onboarding-workflow.md) | 온보딩 자동화 워크플로우 |
| [google-oauth.md](google-oauth.md) | Google OAuth + Drive 연동 |
| [frontend-guide.md](frontend-guide.md) | Frontend 컴포넌트 + 상태 관리 |
