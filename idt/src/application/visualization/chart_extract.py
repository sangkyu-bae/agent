"""chart_router / chart_builder 공용 질문·분석텍스트 추출 헬퍼.

Excel(user_query/analysis_text)과 Supervisor(messages) 양쪽 state 형태를 모두 지원.
"""


def extract_question(state: dict) -> str:
    """최근 user 질문 추출. Excel(user_query) / Supervisor(messages) 모두 지원."""
    if state.get("user_query"):
        return state["user_query"]
    for msg in reversed(state.get("messages", [])):
        role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "type", "")
        if role in ("user", "human"):
            return (
                msg.get("content", "") if isinstance(msg, dict)
                else getattr(msg, "content", "")
            )
    return ""


def extract_analysis_text(state: dict) -> str:
    """직전 분석 텍스트 추출. Excel(analysis_text) / Supervisor(마지막 AIMessage) 지원."""
    if state.get("analysis_text"):
        return state["analysis_text"]
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, dict):
            continue
        if getattr(msg, "type", "") == "ai":
            return getattr(msg, "content", "")
    return ""
