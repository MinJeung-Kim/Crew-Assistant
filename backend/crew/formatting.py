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
