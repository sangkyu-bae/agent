"""chart_router 노드 + route_after_chart_router 테스트."""
from langchain_core.messages import AIMessage, HumanMessage

from src.application.visualization.chart_router import (
    create_chart_router_node,
    route_after_chart_router,
)
from src.domain.visualization.interfaces import VisualizationClassifierInterface
from src.domain.visualization.policies import VisualizationRoutingPolicy


class _NullLogger:
    def debug(self, *a, **k): ...
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...
    def critical(self, *a, **k): ...


class _FakeClassifier(VisualizationClassifierInterface):
    def __init__(self, label: str = "visualize") -> None:
        self.label = label
        self.called = False

    async def classify(self, question: str, analysis_text: str) -> str:
        self.called = True
        return self.label


class _RaisingClassifier(VisualizationClassifierInterface):
    async def classify(self, question: str, analysis_text: str) -> str:
        raise RuntimeError("boom")


def _supervisor_state(question: str, analysis: str) -> dict:
    return {
        "messages": [
            HumanMessage(content=question),
            AIMessage(content=analysis),
        ],
    }


def _excel_state(question: str, analysis: str) -> dict:
    return {"user_query": question, "analysis_text": analysis}


class TestChartRouterHeuristicOnly:
    async def test_explicit_request_skips_classifier(self) -> None:
        classifier = _FakeClassifier("text")
        node = create_chart_router_node(
            VisualizationRoutingPolicy(), _NullLogger(), classifier
        )
        result = await node(_supervisor_state("그래프 그려줘", "내용"))
        assert result["viz_decision"] == "visualize"
        assert classifier.called is False  # 명시요청은 LLM 미호출

    async def test_no_signal_returns_text_without_classifier(self) -> None:
        classifier = _FakeClassifier("visualize")
        node = create_chart_router_node(
            VisualizationRoutingPolicy(), _NullLogger(), classifier
        )
        result = await node(_supervisor_state("요약해줘", "짧은 텍스트"))
        assert result["viz_decision"] == "text"
        assert classifier.called is False


class TestChartRouterAmbiguous:
    async def test_ambiguous_uses_classifier(self) -> None:
        classifier = _FakeClassifier("visualize")
        node = create_chart_router_node(
            VisualizationRoutingPolicy(), _NullLogger(), classifier
        )
        state = _supervisor_state("추세 설명해줘", "2023 100, 2024 130, 2025 160, 12%")
        result = await node(state)
        assert classifier.called is True
        assert result["viz_decision"] == "visualize"

    async def test_ambiguous_without_classifier_defaults_text(self) -> None:
        node = create_chart_router_node(
            VisualizationRoutingPolicy(), _NullLogger(), classifier=None
        )
        state = _supervisor_state("추세 설명해줘", "2023 100, 2024 130, 2025 160, 12%")
        result = await node(state)
        assert result["viz_decision"] == "text"

    async def test_classifier_exception_falls_back_to_text(self) -> None:
        node = create_chart_router_node(
            VisualizationRoutingPolicy(), _NullLogger(), _RaisingClassifier()
        )
        state = _supervisor_state("추세 설명해줘", "2023 100, 2024 130, 2025 160, 12%")
        result = await node(state)
        assert result["viz_decision"] == "text"


class TestStateExtraction:
    async def test_works_with_excel_state(self) -> None:
        node = create_chart_router_node(
            VisualizationRoutingPolicy(), _NullLogger(), None
        )
        result = await node(_excel_state("매출 그래프 그려줘", "내용"))
        assert result["viz_decision"] == "visualize"

    async def test_works_with_supervisor_state(self) -> None:
        node = create_chart_router_node(
            VisualizationRoutingPolicy(), _NullLogger(), None
        )
        result = await node(_supervisor_state("매출 차트 그려줘", "내용"))
        assert result["viz_decision"] == "visualize"


class TestRouteAfterChartRouter:
    def test_visualize(self) -> None:
        assert route_after_chart_router({"viz_decision": "visualize"}) == "visualize"

    def test_text(self) -> None:
        assert route_after_chart_router({"viz_decision": "text"}) == "text"

    def test_empty_defaults_text(self) -> None:
        assert route_after_chart_router({}) == "text"
