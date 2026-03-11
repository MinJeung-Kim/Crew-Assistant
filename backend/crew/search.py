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
                results_text.append(f"{index}. {title}\nURL: {href}\nSummary: {body}")
    except Exception as exc:
        return f"Web search failed ({exc}). Continue with model knowledge only."

    if not results_text:
        return "No web results found. Continue with model knowledge only."

    return "\n\n".join(results_text)
