from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re

ROUTE_KEYWORDS = (
    "트렌드",
    "트랜드",
    "trend",
    "조사",
    "research",
    "보고서",
    "report",
    "analysis",
    "분석",
    "요약",
    "summary",
)

MARKET_KEYWORDS = ("시장", "market", "투자", "investment", "adoption")
POLICY_KEYWORDS = ("규제", "정책", "법", "compliance", "policy", "risk", "리스크")
EXECUTION_KEYWORDS = ("로드맵", "실행", "action plan", "roadmap", "strategy")


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


def should_route_to_crewai(user_query: str) -> bool:
    normalized = user_query.strip().lower()
    return any(keyword in normalized for keyword in ROUTE_KEYWORDS)


def run_dynamic_research_crew(user_query: str, runtime: CrewRuntimeConfig) -> str:
    return run_dynamic_research_crew_with_trace(user_query, runtime).report


def run_dynamic_research_crew_with_trace(
    user_query: str,
    runtime: CrewRuntimeConfig,
) -> CrewExecutionResult:
    # Keep CrewAI import lazy so the API can still boot even if CrewAI is unavailable.
    from crewai import Agent, Crew, LLM, Process, Task  # pylint: disable=import-outside-toplevel

    plan = build_plan(user_query)
    llm = LLM(
        model=resolve_crewai_model(runtime),
        base_url=runtime.llm_base_url,
        api_key=runtime.llm_api_key,
        temperature=0.2,
    )

    agent_map = {
        blueprint.key: Agent(
            role=blueprint.role,
            goal=blueprint.goal,
            backstory=blueprint.backstory,
            llm=llm,
            verbose=False,
            allow_delegation=blueprint.key == "trend_analyst",
        )
        for blueprint in plan.agents
    }
    flow_agents = tuple(
        CrewFlowAgent(id=blueprint.key, role=blueprint.role, goal=blueprint.goal)
        for blueprint in plan.agents
    )
    flow_tasks: list[CrewFlowTask] = []

    web_context = collect_web_context(plan.topic, runtime.web_search_results)

    research_task = Task(
        description=(
            f"User request: {user_query}\n"
            f"Research topic: {plan.topic}\n"
            f"Target year: {plan.target_year}\n"
            f"Output language: {plan.language}.\n"
            "Use the external context when available and gather concrete trend signals,"
            " notable technologies, and practical evidence.\n"
            f"External context:\n{web_context}"
        ),
        expected_output=(
            "A markdown bullet list with at least 10 trend findings. "
            "Each bullet must include why it matters and a source URL if available."
        ),
        agent=agent_map["researcher"],
    )
    research_task_id = "research_task"
    flow_tasks.append(
        CrewFlowTask(
            id=research_task_id,
            title="Collect trend evidence",
            agent_id="researcher",
            depends_on=(),
        )
    )

    trend_task = Task(
        description=(
            "Turn the raw findings into structured trend analysis. "
            "Cluster similar findings, rank their potential business impact, and explain"
            " maturity level (early, growing, mainstream)."
        ),
        expected_output=(
            "A markdown section with trend clusters, impact levels, and short evidence notes."
        ),
        agent=agent_map["trend_analyst"],
        context=[research_task],
    )
    trend_task_id = "trend_analysis_task"
    flow_tasks.append(
        CrewFlowTask(
            id=trend_task_id,
            title="Cluster and prioritize trends",
            agent_id="trend_analyst",
            depends_on=(research_task_id,),
        )
    )

    tasks: list[Task] = [research_task, trend_task]
    report_context: list[Task] = [trend_task]
    report_context_ids: list[str] = [trend_task_id]

    if "market_analyst" in agent_map:
        market_task = Task(
            description=(
                "Analyze market adoption and investment patterns from the trend analysis. "
                "Highlight where budget and adoption are accelerating or slowing down."
            ),
            expected_output=(
                "A markdown section describing market opportunities and watch-outs."
            ),
            agent=agent_map["market_analyst"],
            context=[trend_task],
        )
        tasks.append(market_task)
        report_context.append(market_task)
        market_task_id = "market_analysis_task"
        report_context_ids.append(market_task_id)
        flow_tasks.append(
            CrewFlowTask(
                id=market_task_id,
                title="Analyze market adoption",
                agent_id="market_analyst",
                depends_on=(trend_task_id,),
            )
        )

    if "risk_analyst" in agent_map:
        risk_task = Task(
            description=(
                "Identify policy, legal, ethics, security, and operational risks implied by"
                " the analyzed trends."
            ),
            expected_output=(
                "A markdown section containing risk categories and mitigation suggestions."
            ),
            agent=agent_map["risk_analyst"],
            context=[trend_task],
        )
        tasks.append(risk_task)
        report_context.append(risk_task)
        risk_task_id = "risk_analysis_task"
        report_context_ids.append(risk_task_id)
        flow_tasks.append(
            CrewFlowTask(
                id=risk_task_id,
                title="Assess risks and compliance",
                agent_id="risk_analyst",
                depends_on=(trend_task_id,),
            )
        )

    if "strategy_planner" in agent_map:
        execution_task = Task(
            description=(
                "Create a phased execution roadmap based on the trend and risk analysis."
                " Include 30/90/180-day priorities."
            ),
            expected_output=(
                "A markdown roadmap with phase-based actions and KPI ideas."
            ),
            agent=agent_map["strategy_planner"],
            context=report_context,
        )
        tasks.append(execution_task)
        report_context.append(execution_task)
        execution_task_id = "execution_strategy_task"
        flow_tasks.append(
            CrewFlowTask(
                id=execution_task_id,
                title="Design execution roadmap",
                agent_id="strategy_planner",
                depends_on=tuple(report_context_ids),
            )
        )
        report_context_ids.append(execution_task_id)

    report_task = Task(
        description=(
            "Write a final report in markdown. The report must be polished and easy to read. "
            "Use this exact section order: 1) Executive Summary, 2) 2026 Core Trends, "
            "3) Industry Impact, 4) Opportunities & Risks, 5) Action Recommendations, "
            "6) References."
        ),
        expected_output=(
            "A complete markdown report with headings, bullets, and references."
        ),
        agent=agent_map["report_writer"],
        context=report_context,
    )
    tasks.append(report_task)
    flow_tasks.append(
        CrewFlowTask(
            id="report_task",
            title="Generate final markdown report",
            agent_id="report_writer",
            depends_on=tuple(report_context_ids),
        )
    )

    crew = Crew(
        agents=list(agent_map.values()),
        tasks=tasks,
        process=Process.sequential,
        verbose=False,
    )
    result = crew.kickoff()

    flow_graph = CrewFlowGraph(
        topic=plan.topic,
        target_year=plan.target_year,
        agents=flow_agents,
        tasks=tuple(flow_tasks),
    )
    return CrewExecutionResult(
        report=format_report_output(str(result), plan.language),
        graph=flow_graph,
    )


def crew_graph_to_dict(graph: CrewFlowGraph) -> dict[str, object]:
    return {
        "topic": graph.topic,
        "target_year": graph.target_year,
        "agents": [
            {
                "id": agent.id,
                "role": agent.role,
                "goal": agent.goal,
            }
            for agent in graph.agents
        ],
        "tasks": [
            {
                "id": task.id,
                "title": task.title,
                "agent_id": task.agent_id,
                "depends_on": list(task.depends_on),
            }
            for task in graph.tasks
        ],
    }


def build_plan(user_query: str) -> CrewPlan:
    normalized = user_query.lower()
    target_year = parse_target_year(user_query)
    language = "Korean" if re.search(r"[가-힣]", user_query) else "English"
    topic = extract_topic(user_query)

    include_market = has_any_keyword(normalized, MARKET_KEYWORDS)
    include_policy = has_any_keyword(normalized, POLICY_KEYWORDS)
    include_execution_plan = has_any_keyword(normalized, EXECUTION_KEYWORDS)
    use_web_research = has_any_keyword(normalized, ("트렌드", "트랜드", "trend", "조사", "research", "최신", "latest"))

    agents = [
        AgentBlueprint(
            key="researcher",
            role=f"{target_year} Technology Research Specialist",
            goal="Find reliable, current signals that explain technology shifts.",
            backstory="You are skilled at discovering concise, evidence-backed trend insights.",
        ),
        AgentBlueprint(
            key="trend_analyst",
            role=f"{target_year} IT Trend Intelligence Analyst",
            goal="Convert raw findings into prioritized strategic trends.",
            backstory="You are an analyst who transforms noisy research into clear strategic narratives.",
        ),
    ]

    if include_market:
        agents.append(
            AgentBlueprint(
                key="market_analyst",
                role="Market Adoption Analyst",
                goal="Assess adoption curves and investment momentum.",
                backstory="You connect technology signals to business outcomes and timing.",
            )
        )

    if include_policy:
        agents.append(
            AgentBlueprint(
                key="risk_analyst",
                role="Policy and Risk Analyst",
                goal="Identify compliance and operational risks early.",
                backstory="You track policy and governance implications for emerging technologies.",
            )
        )

    if include_execution_plan:
        agents.append(
            AgentBlueprint(
                key="strategy_planner",
                role="Execution Strategy Planner",
                goal="Translate trends into phased implementation plans.",
                backstory="You design pragmatic roadmaps from complex inputs.",
            )
        )

    agents.append(
        AgentBlueprint(
            key="report_writer",
            role="Senior Technical Report Writer",
            goal="Produce a concise, executive-ready markdown report.",
            backstory="You specialize in structuring long analysis into clear and actionable reports.",
        )
    )

    return CrewPlan(
        topic=topic,
        target_year=target_year,
        language=language,
        include_market=include_market,
        include_policy=include_policy,
        include_execution_plan=include_execution_plan,
        use_web_research=use_web_research,
        agents=tuple(agents),
    )


def parse_target_year(text: str) -> int:
    match = re.search(r"\b(20\d{2})\b", text)
    if match:
        return int(match.group(1))
    return datetime.utcnow().year


def extract_topic(user_query: str) -> str:
    topic = user_query.strip()
    cleanup_patterns = [
        r"보고서\s*형식으로\s*요약해줘",
        r"보고서\s*형식으로\s*정리해줘",
        r"요약해줘",
        r"정리해줘",
        r"조사해줘",
        r"please\s+summarize",
        r"in\s+report\s+format",
    ]
    for pattern in cleanup_patterns:
        topic = re.sub(pattern, "", topic, flags=re.IGNORECASE).strip()

    return topic or user_query.strip()


def has_any_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def collect_web_context(topic: str, max_results: int) -> str:
    try:
        from ddgs import DDGS  # pylint: disable=import-outside-toplevel
    except Exception:
        try:
            from duckduckgo_search import DDGS  # pylint: disable=import-outside-toplevel
        except Exception:
            return "Web search package unavailable. Continue with model knowledge only."

    results_text: list[str] = []
    try:
        with DDGS() as ddgs:
            for index, item in enumerate(ddgs.text(topic, max_results=max_results), start=1):
                title = str(item.get("title") or "Untitled").strip()
                href = str(item.get("href") or "").strip()
                body = str(item.get("body") or "").strip()
                results_text.append(
                    f"{index}. {title}\nURL: {href}\nSummary: {body}"
                )
    except Exception as exc:
        return f"Web search failed ({exc}). Continue with model knowledge only."

    if not results_text:
        return "No web results found. Continue with model knowledge only."

    return "\n\n".join(results_text)


def resolve_crewai_model(runtime: CrewRuntimeConfig) -> str:
    explicit_model = runtime.crewai_model.strip()
    if explicit_model:
        return explicit_model

    base_model = runtime.llm_model.strip()
    if base_model.startswith("openai/"):
        # CrewAI strips the first provider prefix for OpenAI calls.
        # Prefixing once more preserves models like "openai/gpt-oss-120b".
        return f"openai/{base_model}"

    if "/" in base_model:
        return base_model

    return f"openai/{base_model}"


def format_report_output(raw_output: str, language: str) -> str:
    cleaned = raw_output.strip()
    if not cleaned:
        if language == "Korean":
            return "보고서를 생성하지 못했습니다. 잠시 후 다시 시도해주세요."
        return "Failed to generate a report. Please try again."

    header = "# CrewAI Trend Report\n\n"
    if language == "Korean":
        header = "# CrewAI 트렌드 보고서\n\n"

    if cleaned.startswith("#"):
        return cleaned
    return header + cleaned
