"""LLM 호출 전 메시지 배열 정규화.

fix-anthropic-prefill-error D1: Claude 4.6+ 는 메시지 배열이 assistant로
끝나면(=prefill로 해석) 400을 반환한다. LLM 호출 직전 배열이 user로 끝나도록
지시 HumanMessage를 비파괴 append 한다. OpenAI/Ollama에도 무해한 패턴이므로
provider 분기 없이 모든 supervisor 경로에 적용한다.
"""
from langchain_core.messages import HumanMessage

DEFAULT_CONTINUATION = "위 결과를 참고하여 작업을 계속 진행하세요."

_ASSISTANT_ROLES = ("assistant", "ai")


def _tail_role(msg) -> str:
    """dict / LangChain 메시지 양쪽에서 role 추출."""
    if isinstance(msg, dict):
        return str(msg.get("role", ""))
    return str(getattr(msg, "type", ""))


def ensure_user_tail(
    messages: list,
    instruction: str = DEFAULT_CONTINUATION,
) -> list:
    """배열 마지막이 assistant면 지시 HumanMessage를 append한 새 리스트 반환.

    - user/human/tool/system-last → 입력 그대로 반환 (no-op)
    - assistant/ai-last → messages + [HumanMessage(instruction)]
    - 빈 배열 → instruction이 truthy면 [HumanMessage(instruction)], 아니면 그대로
    - 원본 리스트는 변형하지 않는다 (LangGraph state 공유 안전)
    """
    if not messages:
        return [HumanMessage(content=instruction)] if instruction else messages
    if _tail_role(messages[-1]) in _ASSISTANT_ROLES:
        return [*messages, HumanMessage(content=instruction)]
    return messages
