from collections.abc import Callable
from datetime import datetime, timezone
import threading
from typing import Any

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
from .serialization import crew_graph_to_dict


CrewProgressCallback = Callable[[dict[str, Any]], None]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_dynamic_research_crew(user_query: str, runtime: CrewRuntimeConfig) -> str:
    return run_dynamic_research_crew_with_trace(user_query, runtime).report


def run_dynamic_research_crew_with_trace(
    user_query: str,
    runtime: CrewRuntimeConfig,
    progress_callback: CrewProgressCallback | None = None,
) -> CrewExecutionResult:
    # Keep CrewAI import lazy so the API can still boot even if CrewAI is unavailable.
    from crewai import Agent, Crew, LLM, Process, Task  # pylint: disable=import-outside-toplevel
    from crewai.events import crewai_event_bus  # pylint: disable=import-outside-toplevel
    from crewai.events.types.task_events import (  # pylint: disable=import-outside-toplevel
        TaskCompletedEvent,
        TaskFailedEvent,
        TaskStartedEvent,
    )

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
    task_uuid_to_flow_id: dict[str, str] = {}

    web_context = collect_web_context(plan.topic, runtime.web_search_results)

    research_task_id = "research_task"
    research_description = (
        f"User request: {user_query}\n"
        f"Research topic: {plan.topic}\n"
        f"Target year: {plan.target_year}\n"
        f"Output language: {plan.language}.\n"
        "Use the external context when available and gather concrete trend signals,"
        " notable technologies, and practical evidence.\n"
        f"External context:\n{web_context}"
    )
    research_expected_output = (
        "A markdown bullet list with at least 10 trend findings. "
        "Each bullet must include why it matters and a source URL if available."
    )
    research_task = Task(
        name=research_task_id,
        description=research_description,
        expected_output=research_expected_output,
        agent=agent_map["researcher"],
    )
    task_uuid_to_flow_id[str(research_task.id)] = research_task_id
    flow_tasks.append(
        CrewFlowTask(
            id=research_task_id,
            title="Collect trend evidence",
            agent_id="researcher",
            depends_on=(),
            description=(
                "Collect verified technology trend signals and evidence from web context "
                "and known sources."
            ),
            expected_output=research_expected_output,
        )
    )

    trend_task_id = "trend_analysis_task"
    trend_description = (
        "Turn the raw findings into structured trend analysis. "
        "Cluster similar findings, rank their potential business impact, and explain"
        " maturity level (early, growing, mainstream)."
    )
    trend_expected_output = (
        "A markdown section with trend clusters, impact levels, and short evidence notes."
    )
    trend_task = Task(
        name=trend_task_id,
        description=trend_description,
        expected_output=trend_expected_output,
        agent=agent_map["trend_analyst"],
        context=[research_task],
    )
    task_uuid_to_flow_id[str(trend_task.id)] = trend_task_id
    flow_tasks.append(
        CrewFlowTask(
            id=trend_task_id,
            title="Cluster and prioritize trends",
            agent_id="trend_analyst",
            depends_on=(research_task_id,),
            description=(
                "Group similar trends, prioritize by business impact, and classify maturity "
                "to identify near-term and long-term bets."
            ),
            expected_output=trend_expected_output,
        )
    )

    tasks: list[Task] = [research_task, trend_task]
    report_context: list[Task] = [trend_task]
    report_context_ids: list[str] = [trend_task_id]

    if "market_analyst" in agent_map:
        market_task_id = "market_analysis_task"
        market_description = (
            "Analyze market adoption and investment patterns from the trend analysis. "
            "Highlight where budget and adoption are accelerating or slowing down."
        )
        market_expected_output = (
            "A markdown section describing market opportunities and watch-outs."
        )
        market_task = Task(
            name=market_task_id,
            description=market_description,
            expected_output=market_expected_output,
            agent=agent_map["market_analyst"],
            context=[trend_task],
        )
        task_uuid_to_flow_id[str(market_task.id)] = market_task_id
        tasks.append(market_task)
        report_context.append(market_task)
        report_context_ids.append(market_task_id)
        flow_tasks.append(
            CrewFlowTask(
                id=market_task_id,
                title="Analyze market adoption",
                agent_id="market_analyst",
                depends_on=(trend_task_id,),
                description=(
                    "Estimate adoption velocity, spending momentum, and where practical demand "
                    "is strongest across industries."
                ),
                expected_output=market_expected_output,
            )
        )

    if "risk_analyst" in agent_map:
        risk_task_id = "risk_analysis_task"
        risk_description = (
            "Identify policy, legal, ethics, security, and operational risks implied by"
            " the analyzed trends."
        )
        risk_expected_output = (
            "A markdown section containing risk categories and mitigation suggestions."
        )
        risk_task = Task(
            name=risk_task_id,
            description=risk_description,
            expected_output=risk_expected_output,
            agent=agent_map["risk_analyst"],
            context=[trend_task],
        )
        task_uuid_to_flow_id[str(risk_task.id)] = risk_task_id
        tasks.append(risk_task)
        report_context.append(risk_task)
        report_context_ids.append(risk_task_id)
        flow_tasks.append(
            CrewFlowTask(
                id=risk_task_id,
                title="Assess risks and compliance",
                agent_id="risk_analyst",
                depends_on=(trend_task_id,),
                description=(
                    "Assess legal, regulatory, security, and operational risk factors and "
                    "propose practical mitigation checkpoints."
                ),
                expected_output=risk_expected_output,
            )
        )

    if "strategy_planner" in agent_map:
        execution_task_id = "execution_strategy_task"
        execution_description = (
            "Create a phased execution roadmap based on the trend and risk analysis."
            " Include 30/90/180-day priorities."
        )
        execution_expected_output = (
            "A markdown roadmap with phase-based actions and KPI ideas."
        )
        execution_task = Task(
            name=execution_task_id,
            description=execution_description,
            expected_output=execution_expected_output,
            agent=agent_map["strategy_planner"],
            context=report_context,
        )
        task_uuid_to_flow_id[str(execution_task.id)] = execution_task_id
        tasks.append(execution_task)
        report_context.append(execution_task)
        flow_tasks.append(
            CrewFlowTask(
                id=execution_task_id,
                title="Design execution roadmap",
                agent_id="strategy_planner",
                depends_on=tuple(report_context_ids),
                description=(
                    "Convert insights into 30/90/180-day execution plans with owners, "
                    "milestones, and measurable KPIs."
                ),
                expected_output=execution_expected_output,
            )
        )
        report_context_ids.append(execution_task_id)

    report_task_id = "report_task"
    report_description = (
        "Write a final report in markdown. The report must be polished and easy to read. "
        "Use this exact section order: 1) Executive Summary, 2) 2026 Core Trends, "
        "3) Industry Impact, 4) Opportunities & Risks, 5) Action Recommendations, "
        "6) References."
    )
    report_expected_output = (
        "A complete markdown report with headings, bullets, and references."
    )
    report_task = Task(
        name=report_task_id,
        description=report_description,
        expected_output=report_expected_output,
        agent=agent_map["report_writer"],
        context=report_context,
    )
    task_uuid_to_flow_id[str(report_task.id)] = report_task_id
    tasks.append(report_task)
    flow_tasks.append(
        CrewFlowTask(
            id=report_task_id,
            title="Generate final markdown report",
            agent_id="report_writer",
            depends_on=tuple(report_context_ids),
            description=(
                "Synthesize all upstream analyses into a complete business report with "
                "clear recommendations and references."
            ),
            expected_output=report_expected_output,
        )
    )

    flow_graph = CrewFlowGraph(
        topic=plan.topic,
        target_year=plan.target_year,
        agents=flow_agents,
        tasks=tuple(flow_tasks),
    )

    task_statuses: dict[str, str] = {task.id: "pending" for task in flow_graph.tasks}
    task_meta = {
        task.id: {
            "title": task.title,
            "agent_id": task.agent_id,
        }
        for task in flow_graph.tasks
    }
    progress_lock = threading.Lock()

    def emit_progress(
        phase: str,
        active_task_id: str | None,
        detail: str | None = None,
        include_graph: bool = False,
    ) -> None:
        if progress_callback is None:
            return

        with progress_lock:
            tasks_payload = [
                {
                    "task_id": task.id,
                    "title": task.title,
                    "agent_id": task.agent_id,
                    "status": task_statuses.get(task.id, "pending"),
                }
                for task in flow_graph.tasks
            ]

        payload: dict[str, Any] = {
            "phase": phase,
            "active_task_id": active_task_id,
            "active_agent_id": (
                task_meta.get(active_task_id, {}).get("agent_id")
                if active_task_id
                else None
            ),
            "detail": detail,
            "updated_at": utc_now_iso(),
            "tasks": tasks_payload,
        }
        if include_graph:
            payload["crew_graph"] = crew_graph_to_dict(flow_graph)

        progress_callback(payload)

    def resolve_flow_task_id(event_task: Any) -> str | None:
        task_uuid = getattr(event_task, "id", None)
        if task_uuid is None:
            return None
        return task_uuid_to_flow_id.get(str(task_uuid))

    def on_task_started(_: Any, event: Any) -> None:
        flow_task_id = resolve_flow_task_id(getattr(event, "task", None))
        if not flow_task_id:
            return
        with progress_lock:
            task_statuses[flow_task_id] = "running"
        emit_progress(
            phase="running",
            active_task_id=flow_task_id,
            detail=f"{task_meta[flow_task_id]['title']} is running",
        )

    def on_task_completed(_: Any, event: Any) -> None:
        flow_task_id = resolve_flow_task_id(getattr(event, "task", None))
        if not flow_task_id:
            return
        with progress_lock:
            task_statuses[flow_task_id] = "completed"
        emit_progress(
            phase="task_completed",
            active_task_id=None,
            detail=f"{task_meta[flow_task_id]['title']} completed",
        )

    def on_task_failed(_: Any, event: Any) -> None:
        flow_task_id = resolve_flow_task_id(getattr(event, "task", None))
        if not flow_task_id:
            return
        error_message = str(getattr(event, "error", "Task failed"))
        with progress_lock:
            task_statuses[flow_task_id] = "failed"
        emit_progress(
            phase="task_failed",
            active_task_id=flow_task_id,
            detail=error_message,
        )

    crew = Crew(
        agents=list(agent_map.values()),
        tasks=tasks,
        process=Process.sequential,
        verbose=False,
    )
    if progress_callback is not None:
        crewai_event_bus.register_handler(TaskStartedEvent, on_task_started)
        crewai_event_bus.register_handler(TaskCompletedEvent, on_task_completed)
        crewai_event_bus.register_handler(TaskFailedEvent, on_task_failed)
        emit_progress(
            phase="graph_ready",
            active_task_id=None,
            detail="Crew plan prepared",
            include_graph=True,
        )

    try:
        result = crew.kickoff()
    finally:
        if progress_callback is not None:
            crewai_event_bus.off(TaskStartedEvent, on_task_started)
            crewai_event_bus.off(TaskCompletedEvent, on_task_completed)
            crewai_event_bus.off(TaskFailedEvent, on_task_failed)

    if progress_callback is not None:
        with progress_lock:
            for task_id, status in task_statuses.items():
                if status == "running":
                    task_statuses[task_id] = "completed"
        emit_progress(
            phase="crew_completed",
            active_task_id=None,
            detail="Crew execution completed",
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
