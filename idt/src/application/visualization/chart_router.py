"""분석 노드 직후 시각화 vs 텍스트를 판단만 하는 라우터 노드.

라우터는 state["viz_decision"]만 갱신한다. 차트 생성/렌더링은 하지 않으며,
실제 분기 처리는 이후 별도 노드가 viz_decision을 읽어 수행한다.
"""
from src.application.visualization.chart_extract import (
    extract_analysis_text,
    extract_question,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.visualization.interfaces import VisualizationClassifierInterface
from src.domain.visualization.policies import VisualizationRoutingPolicy
from src.domain.visualization.schemas import VizDecision

_VALID = {VizDecision.VISUALIZE.value, VizDecision.TEXT.value}


def create_chart_router_node(
    policy: VisualizationRoutingPolicy,
    logger: LoggerInterface,
    classifier: VisualizationClassifierInterface | None = None,
):
    """시각화/텍스트 판단 라우터 노드 팩토리.

    Args:
        policy: 휴리스틱 1차 판단 정책
        logger: 로거
        classifier: 애매구간 LLM 분류기 (없으면 애매구간은 보수적으로 text)

    Returns:
        LangGraph 노드 함수 (state -> {"viz_decision": ...})
    """

    async def chart_router(state: dict) -> dict:
        question = extract_question(state)
        analysis_text = extract_analysis_text(state)

        decision = policy.decide(question, analysis_text)

        if decision is None:
            decision = await _resolve_ambiguous(
                classifier, question, analysis_text, logger
            )

        if decision not in _VALID:
            decision = VizDecision.TEXT.value

        logger.info("chart_router decided", decision=decision)
        return {"viz_decision": decision}

    return chart_router


async def _resolve_ambiguous(
    classifier: VisualizationClassifierInterface | None,
    question: str,
    analysis_text: str,
    logger: LoggerInterface,
) -> str:
    """애매구간 처리: classifier가 있으면 LLM 분류, 없거나 실패하면 text."""
    if classifier is None:
        return VizDecision.TEXT.value
    try:
        return await classifier.classify(question, analysis_text)
    except Exception as e:
        logger.error("chart_router classify failed, fallback=text", exception=e)
        return VizDecision.TEXT.value


def route_after_chart_router(state: dict) -> str:
    """후속 분기용 순수 라우팅 함수.

    현재 그래프 배선에서는 미사용. 후속 차트 처리 노드 도입 시
    conditional edge에 부착하여 사용한다.
    """
    if state.get("viz_decision") == VizDecision.VISUALIZE.value:
        return "visualize"
    return "text"
