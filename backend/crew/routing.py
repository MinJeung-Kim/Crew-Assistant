from .constants import ROUTE_KEYWORDS


def should_route_to_crewai(user_query: str) -> bool:
    normalized = user_query.strip().lower()
    return any(keyword in normalized for keyword in ROUTE_KEYWORDS)
