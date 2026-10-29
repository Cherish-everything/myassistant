from tools import basic_web_search, get_weather_forecast, execute_deep_research


def _extract_text(args, *keys):
    if args is None:
        return ""
    if isinstance(args, str):
        return args.strip()
    if isinstance(args, dict):
        for key in keys:
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for value in args.values():
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _fallback_prompt(ui_context):
    if ui_context is None:
        return ""
    for attr in ("current_user_prompt", "user_prompt", "prompt", "text"):
        value = getattr(ui_context, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def run_research_agent(ui_context, tool_name, args):
    """Handles everything related to research, news, and daily reports"""

    if tool_name == "basic_web_search":
        query_string = _extract_text(args, "query", "search_query", "search_term", "question", "text", "input", "topic")
        if not query_string:
            query_string = _fallback_prompt(ui_context)

        if not query_string:
            return "RESEARCH FAILURE // Search payload data vector is empty."

        return basic_web_search(query_string)

    elif tool_name == "execute_deep_research":
        query = _extract_text(args, "query", "search_query", "search_term", "question", "text", "input", "topic")
        if not query:
            query = _fallback_prompt(ui_context)

        if not query:
            return "RESEARCH FAILURE // Deep research query data vector is empty."

        if isinstance(args, dict):
            scan_keyword = _extract_text(args, "scan_keyword", "keyword")
            suggested_filename = _extract_text(args, "suggested_filename", "filename") or "Research_Report.md"
        else:
            scan_keyword = None
            suggested_filename = "Research_Report.md"

        return execute_deep_research(query=query, scan_keyword=scan_keyword, suggested_filename=suggested_filename)

    elif tool_name == "get_weather_forecast":
        location = _extract_text(args, "location", "city", "place")
        if not location:
            location = _fallback_prompt(ui_context)

        days = args.get("days", 1) if isinstance(args, dict) else 1

        if not location:
            return "RESEARCH FAILURE // Location data is empty."

        return get_weather_forecast(location, days)

    return f"Research Agent: Operation '{tool_name}' completed."