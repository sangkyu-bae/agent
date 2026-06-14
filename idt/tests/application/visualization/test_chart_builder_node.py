"""chart_builder 노드 단위 테스트 (supervisor-chart-builder-node Design §11-1)."""
from langchain_core.messages import AIMessage, HumanMessage

from src.application.visualization.chart_builder_node import (
    create_chart_builder_node,
)
from src.domain.visualization.chart_schemas import (
    ChartConfig,
    ChartData,
    ChartDataset,
    ChartType,
)
from src.domain.visualization.interfaces import ChartBuilderInterface


class _NullLogger:
    def debug(self, *a, **k): ...
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...
    def critical(self, *a, **k): ...


def _sample_config() -> ChartConfig:
    return ChartConfig(
        type=ChartType.BAR,
        data=ChartData(
            labels=["2023", "2024"],
            datasets=[ChartDataset(label="매출", data=[100.0, 130.0])],
        ),
        options={"responsive": True},
    )


class _FakeBuilder(ChartBuilderInterface):
    def __init__(self, configs: list[ChartConfig] | None = None) -> None:
        self._configs = configs if configs is not None else [_sample_config()]
        self.called = False
        self.last_args: tuple = ()

    async def build(
        self, question: str, analysis_text: str, context: str = "",
    ) -> list[ChartConfig]:
        self.called = True
        self.last_args = (question, analysis_text, context)
        return list(self._configs)


class _RaisingBuilder(ChartBuilderInterface):
    async def build(
        self, question: str, analysis_text: str, context: str = "",
    ) -> list[ChartConfig]:
        raise RuntimeError("boom")


def _state(viz: str) -> dict:
    return {
        "messages": [
            HumanMessage(content="매출 그래프 그려줘"),
            AIMessage(content="2023 100, 2024 130"),
        ],
        "viz_decision": viz,
    }


class TestChartBuilderVisualize:
    async def test_builds_charts_when_visualize(self) -> None:
        builder = _FakeBuilder()
        node = create_chart_builder_node(builder, _NullLogger())
        result = await node(_state("visualize"))

        assert builder.called is True
        assert len(result["charts"]) == 1
        assert result["charts"][0]["type"] == "bar"
        assert result["visualization_done"] is True

    async def test_charts_are_plain_dicts(self) -> None:
        node = create_chart_builder_node(_FakeBuilder(), _NullLogger())
        result = await node(_state("visualize"))
        assert all(isinstance(c, dict) for c in result["charts"])


class TestChartBuilderTextBranch:
    async def test_text_branch_skips_builder(self) -> None:
        builder = _FakeBuilder()
        node = create_chart_builder_node(builder, _NullLogger())
        result = await node(_state("text"))

        assert builder.called is False
        assert result["visualization_done"] is True
        assert "charts" not in result


class TestChartBuilderGraceful:
    async def test_builder_exception_returns_empty_charts(self) -> None:
        node = create_chart_builder_node(_RaisingBuilder(), _NullLogger())
        result = await node(_state("visualize"))
        assert result["charts"] == []
        assert result["visualization_done"] is True


class TestChartBuilderInvariants:
    async def test_does_not_touch_messages_or_last_worker(self) -> None:
        node = create_chart_builder_node(_FakeBuilder(), _NullLogger())
        result = await node(_state("visualize"))
        assert set(result.keys()) == {"charts", "visualization_done"}
        assert "messages" not in result
        assert "last_worker_id" not in result
