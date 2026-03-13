# CrewAI 멀티 에이전트 오케스트레이션

## 개요

사용자가 트렌드/리서치/보고서 관련 쿼리를 입력하면 CrewAI 프레임워크를 통해 멀티 에이전트 파이프라인이 동적으로 구성되어 실행됩니다. 각 에이전트는 특정 역할을 맡아 순차적으로 태스크를 수행하고, 최종적으로 마크다운 보고서를 생성합니다.

---

## 모듈 구조

```
backend/crew/
├── __init__.py          # should_route_to_crewai 외부 export
├── constants.py         # 라우팅/에이전트 구성 키워드
├── routing.py           # 쿼리 → CrewAI 라우팅 판단
├── models.py            # 데이터 모델 (frozen dataclass)
├── planning.py          # 동적 에이전트/태스크 계획 수립
├── search.py            # DuckDuckGo 웹 검색
├── execution.py         # Crew 실행 + 프로그레스 콜백
├── formatting.py        # 보고서 마크다운 포맷팅
└── serialization.py     # 직렬화 유틸리티
```

---

## 실행 흐름

```
사용자 쿼리
    │
    ▼
┌─────────────────────────────────────────┐
│ 1. Routing (routing.py)                  │
│    should_route_to_crewai(query)         │
│    → 키워드 매칭으로 CrewAI 사용 여부 판단  │
└──────────────┬──────────────────────────┘
               │ True
               ▼
┌─────────────────────────────────────────┐
│ 2. Planning (planning.py)                │
│    plan_crew(query, config)              │
│    → 토픽, 연도, 언어 추출               │
│    → 키워드 분석 → 에이전트 동적 구성     │
│    → CrewPlan 반환                       │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 3. Web Search (search.py)                │
│    run_web_search(topic, max_results)    │
│    → DuckDuckGo API 호출                 │
│    → 검색 결과 텍스트 포맷팅              │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 4. Execution (execution.py)              │
│    execute_crew(plan, config, callback)  │
│    → CrewAI Agent + Task 생성            │
│    → 태스크 의존성 기반 순차 실행          │
│    → 프로그레스 콜백 → SSE 전송           │
│    → CrewExecutionResult 반환            │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 5. Formatting (formatting.py)            │
│    → 최종 보고서 마크다운 후처리          │
│    → 언어별 헤더 (한국어/영어)            │
└─────────────────────────────────────────┘
```

---

## 라우팅 (routing.py)

### `should_route_to_crewai(user_query: str) -> bool`

사용자 쿼리를 소문자로 정규화한 후 키워드 매칭으로 CrewAI 라우팅 여부를 결정합니다.

### 라우팅 키워드 (constants.py)

```python
ROUTE_KEYWORDS = (
    "트렌드", "트랜드", "trend",
    "조사", "research",
    "보고서", "report",
    "analysis", "분석",
    "요약", "summary",
)
```

**예시 트리거 쿼리:**
- `"2026년 IT 트렌드 조사해서 보고서 형식으로 요약해줘"`
- `"AI market trend analysis report"`
- `"최신 클라우드 기술 분석 보고서"`

---

## 계획 수립 (planning.py)

### `plan_crew(query: str, config: CrewRuntimeConfig) -> CrewPlan`

사용자 쿼리를 분석하여 `CrewPlan`을 생성합니다.

#### 쿼리 분석

| 추출 항목 | 방법 | 기본값 |
|-----------|------|--------|
| **토픽** | 쿼리 전체 (키워드 제거) | 쿼리 원문 |
| **연도** | 정규식 `20\d{2}` 매칭 | 현재 연도 |
| **언어** | 한글 문자 존재 여부 | `"ko"` / `"en"` |

#### 동적 에이전트 구성

쿼리에 포함된 키워드에 따라 에이전트가 동적으로 추가됩니다:

| 에이전트 | 조건 | 키워드 |
|----------|------|--------|
| **Researcher** | 항상 포함 | - |
| **Trend Analyst** | 항상 포함 | - |
| **Market Analyst** | 키워드 감지 시 | `시장`, `market`, `투자`, `investment`, `adoption` |
| **Risk Analyst** | 키워드 감지 시 | `규제`, `정책`, `법`, `compliance`, `policy`, `risk`, `리스크` |
| **Strategy Planner** | 키워드 감지 시 | `로드맵`, `실행`, `action plan`, `roadmap`, `strategy` |
| **Report Writer** | 항상 포함 | - |

#### 키워드 상수

```python
MARKET_KEYWORDS = ("시장", "market", "투자", "investment", "adoption")
POLICY_KEYWORDS = ("규제", "정책", "법", "compliance", "policy", "risk", "리스크")
EXECUTION_KEYWORDS = ("로드맵", "실행", "action plan", "roadmap", "strategy")
```

---

## 데이터 모델 (models.py)

모든 모델은 `frozen=True` dataclass로 불변 객체입니다.

### CrewRuntimeConfig

```python
@dataclass(frozen=True)
class CrewRuntimeConfig:
    llm_model: str           # LLM 모델 ID
    llm_base_url: str        # LLM API URL
    llm_api_key: str         # LLM API 키
    crewai_model: str        # CrewAI 전용 모델 (비어있으면 openai/<llm_model>)
    web_search_results: int  # DuckDuckGo 검색 결과 수
```

### AgentBlueprint

```python
@dataclass(frozen=True)
class AgentBlueprint:
    key: str        # 에이전트 고유 ID (예: "researcher")
    role: str       # 역할명 (예: "Researcher")
    goal: str       # 목표 설명
    backstory: str  # 배경 설명
```

### CrewPlan

```python
@dataclass(frozen=True)
class CrewPlan:
    topic: str                       # 연구 주제
    target_year: int                 # 대상 연도
    language: str                    # 출력 언어 ("ko" / "en")
    include_market: bool             # 시장 분석 포함 여부
    include_policy: bool             # 정책/리스크 분석 포함 여부
    include_execution_plan: bool     # 실행 전략 포함 여부
    use_web_research: bool           # 웹 검색 사용 여부
    agents: tuple[AgentBlueprint, ...]  # 에이전트 목록
```

### CrewFlowGraph (프론트엔드 전송용)

```python
@dataclass(frozen=True)
class CrewFlowGraph:
    topic: str
    target_year: int
    agents: tuple[CrewFlowAgent, ...]
    tasks: tuple[CrewFlowTask, ...]
```

### CrewFlowTask

```python
@dataclass(frozen=True)
class CrewFlowTask:
    id: str                          # 태스크 ID
    title: str                       # 표시 제목
    agent_id: str                    # 담당 에이전트 ID
    depends_on: tuple[str, ...]      # 선행 태스크 ID
    description: str = ""            # 태스크 설명
    expected_output: str = ""        # 예상 출력
```

---

## 태스크 의존성 그래프

```
┌──────────────┐
│  Researcher  │ ← 웹 검색 결과 입력
│  (Research)  │
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│  Trend Analyst   │
│ (Trend Analysis) │
└──┬───────┬───┬───┘
   │       │   │
   ▼       ▼   ▼
┌──────┐ ┌──────┐ ┌──────────────┐      (조건부)
│Market│ │Risk  │ │Strategy Plan │
│Analyst│ │Analyst│ │ (depends:   │
│      │ │      │ │  market+risk)│
└──┬───┘ └──┬───┘ └──────┬───────┘
   │        │             │
   └────────┴─────────────┘
            │
            ▼
   ┌─────────────────┐
   │  Report Writer   │
   │ (최종 보고서)     │
   └─────────────────┘
```

- **Market Analyst**, **Risk Analyst**: Trend Analysis 완료 후 병렬 투입 가능
- **Strategy Planner**: Market + Risk 모두 완료 후 실행 (전체 분석 기반)
- **Report Writer**: 모든 분석 태스크 완료 후 최종 보고서 합성

---

## 웹 검색 (search.py)

### `run_web_search(topic: str, max_results: int) -> str`

DuckDuckGo(ddgs) 라이브러리를 사용하여 주제 관련 웹 검색을 수행합니다.

**검색 결과 포맷:**
```
1. [제목]
URL: https://example.com/article
Summary: 검색 결과 요약 텍스트...

2. [제목]
URL: ...
Summary: ...
```

**설정:**
- `CREWAI_WEB_SEARCH_RESULTS`: 검색 결과 수 (기본 6, 범위 1~12)
- 검색 실패 시 빈 문자열 반환 (graceful degradation)

---

## 실행 (execution.py)

### `execute_crew(plan, config, progress_callback) -> CrewExecutionResult`

CrewAI 프레임워크를 사용하여 에이전트/태스크를 생성하고 실행합니다.

#### 프로그레스 콜백

실행 중 `progress_callback` 함수가 호출되어 SSE로 진행 상황이 전달됩니다.

**이벤트 타입:**

| Phase | 설명 |
|-------|------|
| `graph_ready` | DAG 그래프 생성 완료, `crew_graph` 포함 |
| `running` | 태스크 실행 중, `active_task_id` + `active_agent_id` |
| `task_completed` | 개별 태스크 완료 |
| `task_failed` | 개별 태스크 실패 |
| `crew_completed` | 전체 Crew 실행 완료 |

#### CrewAI 이벤트 버스

`crewai_event_bus`를 통해 태스크 라이프사이클 훅을 수신하여 프로그레스 이벤트를 생성합니다.

---

## 포맷팅 (formatting.py)

최종 보고서를 마크다운으로 후처리합니다.

**언어별 헤더:**
- 한국어(ko): `# CrewAI 트렌드 보고서`
- 영어(en): `# CrewAI Trend Report`

---

## 직렬화 (serialization.py)

`CrewFlowGraph`, `CrewFlowAgent`, `CrewFlowTask` 등 frozen dataclass를 JSON 직렬화 가능한 dict로 변환하는 유틸리티입니다. SSE 페이로드 생성 시 사용됩니다.

---

## 설정

| 환경 변수 | 기본값 | 설명 |
|-----------|--------|------|
| `CREWAI_ENABLED` | `true` | CrewAI 기능 활성화 |
| `CREWAI_MODEL` | `""` (비어있으면 `openai/<LLM_MODEL>`) | CrewAI 전용 모델 |
| `CREWAI_WEB_SEARCH_RESULTS` | `6` | DuckDuckGo 검색 결과 수 (1~12) |

---

## 사용 예시

### 기본 리서치 쿼리

```
2026년 IT 트렌드 조사해서 보고서 형식으로 요약해줘
```

→ Researcher + Trend Analyst + Report Writer (3개 에이전트)

### 시장 + 정책 분석 쿼리

```
2026년 AI 시장 트렌드와 규제 정책 분석 보고서
```

→ Researcher + Trend Analyst + Market Analyst + Risk Analyst + Report Writer (5개 에이전트)

### 전체 분석 쿼리

```
2026년 클라우드 기술 트렌드 시장 분석, 규제 리스크, 실행 로드맵 포함 종합 보고서
```

→ Researcher + Trend Analyst + Market Analyst + Risk Analyst + Strategy Planner + Report Writer (6개 에이전트)
