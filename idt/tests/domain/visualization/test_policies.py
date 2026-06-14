"""VisualizationRoutingPolicy 테스트. Domain: mock 금지, 순수 단위테스트."""
from src.domain.visualization.policies import VisualizationRoutingPolicy
from src.domain.visualization.schemas import VizDecision


class TestExplicitRequest:
    """명시 키워드 감지."""

    def test_keyword_graph_korean(self) -> None:
        policy = VisualizationRoutingPolicy()
        assert policy.explicit_request("매출 추이 그래프 그려줘") is True

    def test_keyword_chart_english(self) -> None:
        policy = VisualizationRoutingPolicy()
        assert policy.explicit_request("draw a CHART for revenue") is True

    def test_no_keyword(self) -> None:
        policy = VisualizationRoutingPolicy()
        assert policy.explicit_request("매출이 얼마인지 알려줘") is False

    def test_empty_question(self) -> None:
        policy = VisualizationRoutingPolicy()
        assert policy.explicit_request("") is False


class TestDataSuggestsChart:
    """수치 신호 휴리스틱."""

    def test_enough_numbers(self) -> None:
        policy = VisualizationRoutingPolicy()
        text = "2023년 100억, 2024년 130억, 2025년 160억으로 12% 증가"
        assert policy.data_suggests_chart(text) is True

    def test_few_numbers(self) -> None:
        policy = VisualizationRoutingPolicy()
        assert policy.data_suggests_chart("매출은 100억입니다") is False

    def test_empty_text(self) -> None:
        policy = VisualizationRoutingPolicy()
        assert policy.data_suggests_chart("") is False

    def test_threshold_boundary(self) -> None:
        policy = VisualizationRoutingPolicy()
        # 정확히 임계값(4)개 → True
        assert policy.data_suggests_chart("1 2 3 4") is True
        # 3개 → False
        assert policy.data_suggests_chart("1 2 3") is False


class TestDecide:
    """1차 판단 (visualize / text / None)."""

    def test_explicit_request_returns_visualize(self) -> None:
        policy = VisualizationRoutingPolicy()
        assert policy.decide("그래프 그려줘", "아무 텍스트") == VizDecision.VISUALIZE.value

    def test_no_signal_returns_text(self) -> None:
        policy = VisualizationRoutingPolicy()
        assert policy.decide("요약해줘", "간단한 설명 텍스트") == VizDecision.TEXT.value

    def test_data_signal_without_keyword_returns_none(self) -> None:
        policy = VisualizationRoutingPolicy()
        text = "2023 100, 2024 130, 2025 160, 12% 증가"
        assert policy.decide("추세 설명해줘", text) is None

    def test_explicit_request_takes_priority_over_data(self) -> None:
        policy = VisualizationRoutingPolicy()
        text = "1 2 3 4 5"
        # 명시 키워드가 있으면 데이터 신호와 무관하게 visualize
        assert policy.decide("차트로 보여줘", text) == VizDecision.VISUALIZE.value
