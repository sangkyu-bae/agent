"""viz_decision="visualize"일 때만 Chart.js config를 생성하는 노드.

차트 생성과 그래프 흐름 제어를 분리한다: 이 노드는 state["charts"]만 채우고
visualization_done=True를 세팅하며, messages/last_worker_id는 건드리지 않는다.
→ 직후 quality_gate가 분석 텍스트(직전 AIMessage)를 평가하므로 차트 노드가
  품질검증 재시도(루프)를 유발하지 않는다.

모든 실패는 빈 결과로 graceful degrade — 텍스트 답변 본 흐름을 절대 막지 않는다.

supervisor-chart-builder-node Design §4.
"""
from src.application.visualization.chart_extract import (
    extract_analysis_text,
    extract_question,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.visualization.interfaces import ChartBuilderInterface
from src.domain.visualization.schemas import VizDecision


def create_chart_builder_node(
    builder: ChartBuilderInterface,
    logger: LoggerInterface,
):
    """차트 생성 노드 팩토리.

    Args:
        builder: 분석텍스트 → Chart.js config 빌더
        logger: 로거

    Returns:
        LangGraph 노드 함수 (state -> {"charts": [...], "visualization_done": True})
    """

    async def chart_builder(state: dict) -> dict:
        if state.get("viz_decision") != VizDecision.VISUALIZE.value:
            # 텍스트 분기는 라우팅상 이 노드를 타지 않으나 방어적으로 처리.
            return {"visualization_done": True}

        question = extract_question(state)
        analysis_text = extract_analysis_text(state)

        try:
            configs = await builder.build(question, analysis_text, context="")
            charts = [c.model_dump(exclude_none=True) for c in configs]
        except Exception as e:
            logger.error("chart_builder failed, fallback []", exception=e)
            charts = []

        logger.info("chart_builder done", chart_count=len(charts))
        return {"charts": charts, "visualization_done": True}

    return chart_builder
