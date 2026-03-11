from datetime import datetime
import re

from .constants import EXECUTION_KEYWORDS, MARKET_KEYWORDS, POLICY_KEYWORDS
from .models import AgentBlueprint, CrewPlan


def build_plan(user_query: str) -> CrewPlan:
    normalized = user_query.lower()
    target_year = parse_target_year(user_query)
    language = "Korean" if re.search(r"[가-힣]", user_query) else "English"
    topic = extract_topic(user_query)

    include_market = has_any_keyword(normalized, MARKET_KEYWORDS)
    include_policy = has_any_keyword(normalized, POLICY_KEYWORDS)
    include_execution_plan = has_any_keyword(normalized, EXECUTION_KEYWORDS)
    use_web_research = has_any_keyword(
        normalized,
        ("트렌드", "트랜드", "trend", "조사", "research", "최신", "latest"),
    )

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
