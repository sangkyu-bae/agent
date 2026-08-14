"""LangGraph 의도 분석 노드 팩토리 — 탈착 이음매.

Design Ref: §2.4 / FR-08 / FR-09. create_chart_router_node 선례를 따르되,
**analyzer 미주입 시 None 을 반환**하는 점이 다르다. 호출측은 그 None 을 보고
add_node 자체를 건너뛰므로, 노드가 그래프에 존재조차 하지 않는다 — 이것이
"끼웠다 뺐다"의 실제 구현이다.

Plan SC: 반환 dict 는 state_key 단 1개만 갱신한다. intent 노드는 워커가 아니므로
messages 를 만들지 않는다 (위키 supervisor 계약 1 — 워커 산출물 오염 방지).

이번 사이클에서는 어떤 그래프에도 배선하지 않는다 (Plan D8). 1차 배선 후보와
2단계 진입 절차는 Design §11.4 참조.
"""
from collections.abc import Awaitable, Callable

from src.domain.intent.interfaces import IntentAnalyzerInterface
from src.domain.intent.policies import IntentResultPolicy
from src.domain.intent.schemas import IntentSpec, Turn
from src.domain.logging.interfaces.logger_interface import LoggerInterface

IntentNode = Callable[[dict], Awaitable[dict]]

_DEFAULT_STATE_KEY = "intent"
_DEFAULT_MESSAGE_KEY = "question"


def create_intent_node(
    analyzer: IntentAnalyzerInterface | None,
    spec: IntentSpec,
    logger: LoggerInterface,
    state_key: str = _DEFAULT_STATE_KEY,
    message_key: str = _DEFAULT_MESSAGE_KEY,
    history_key: str | None = None,
) -> IntentNode | None:
    """의도 분석 노드를 만든다.

    Args:
        analyzer: 판정 포트. **None 이면 None 을 반환한다** — 호출측은 이 경우
            `add_node` 를 하지 않아야 한다 (FR-09).
        spec: 이 노드가 사용할 분류 체계. 그래프마다 다를 수 있다.
        logger: 구조화 로거
        state_key: 결과를 기록할 state 키. 이 키 **하나만** 갱신한다.
        message_key: 판정 대상 메시지를 읽어올 state 키
        history_key: 대화 이력을 읽어올 state 키. None 이면 이력 없이 판정한다.

    Returns:
        LangGraph 노드 함수, 또는 analyzer 가 없으면 None.
    """
    if analyzer is None:
        return None

    async def intent_node(state: dict) -> dict:
        message = _extract_message(state, message_key)
        if not message:
            logger.warning("intent node skipped: no message in state", key=message_key)
            return {state_key: IntentResultPolicy.degraded().model_dump()}

        result = await analyzer.analyze(
            message=message,
            spec=spec,
            history=_extract_history(state, history_key),
        )
        return {state_key: result.model_dump()}

    return intent_node


def _extract_message(state: dict, message_key: str) -> str:
    value = state.get(message_key)
    return value.strip() if isinstance(value, str) else ""


def _extract_history(state: dict, history_key: str | None) -> list[Turn] | None:
    """state 의 이력을 Turn 리스트로 변환한다. 형식이 다르면 조용히 무시한다."""
    if history_key is None:
        return None
    raw = state.get(history_key)
    if not isinstance(raw, list):
        return None
    turns = [_to_turn(item) for item in raw]
    return [turn for turn in turns if turn is not None] or None


def _to_turn(item: object) -> Turn | None:
    if isinstance(item, Turn):
        return item
    if not isinstance(item, dict):
        return None
    try:
        return Turn.model_validate(item)
    except ValueError:
        return None
