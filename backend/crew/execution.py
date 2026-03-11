from .formatting import format_report_output
from .models import (
    CrewExecutionResult,
    CrewFlowAgent,
    CrewFlowGraph,
    CrewFlowTask,
    CrewRuntimeConfig,
)
from .planning import build_plan
from .search import collect_web_context


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
            expected_output=("A markdown roadmap with phase-based actions and KPI ideas."),
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
        expected_output=("A complete markdown report with headings, bullets, and references."),
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
