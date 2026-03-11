from dataclasses import dataclass


@dataclass(frozen=True)
class CrewRuntimeConfig:
    llm_model: str
    llm_base_url: str
    llm_api_key: str
    crewai_model: str
    web_search_results: int


@dataclass(frozen=True)
class AgentBlueprint:
    key: str
    role: str
    goal: str
    backstory: str


@dataclass(frozen=True)
class CrewPlan:
    topic: str
    target_year: int
    language: str
    include_market: bool
    include_policy: bool
    include_execution_plan: bool
    use_web_research: bool
    agents: tuple[AgentBlueprint, ...]


@dataclass(frozen=True)
class CrewFlowAgent:
    id: str
    role: str
    goal: str


@dataclass(frozen=True)
class CrewFlowTask:
    id: str
    title: str
    agent_id: str
    depends_on: tuple[str, ...]
    description: str = ""
    expected_output: str = ""


@dataclass(frozen=True)
class CrewFlowGraph:
    topic: str
    target_year: int
    agents: tuple[CrewFlowAgent, ...]
    tasks: tuple[CrewFlowTask, ...]


@dataclass(frozen=True)
class CrewExecutionResult:
    report: str
    graph: CrewFlowGraph
