"""ExcelAnalysisWorkflow chart_builder 배선 테스트 (supervisor-chart-builder-node §11-5).

그래프 구조만 검증한다(노드 함수는 호출하지 않으므로 의존성은 MagicMock으로 충분).
"""
from unittest.mock import MagicMock

from src.application.workflows.excel_analysis_workflow import ExcelAnalysisWorkflow
from src.domain.policies.analysis_policy import (
    AnalysisQualityThreshold,
    AnalysisRetryPolicy,
)
from src.domain.visualization.chart_schemas import (
    ChartConfig,
    ChartData,
    ChartDataset,
    ChartType,
)
from src.domain.visualization.interfaces import ChartBuilderInterface


class _FakeBuilder(ChartBuilderInterface):
    async def build(self, question, analysis_text, context=""):
        return [
            ChartConfig(
                type=ChartType.BAR,
                data=ChartData(
                    labels=["a"], datasets=[ChartDataset(label="x", data=[1.0])]
                ),
            )
        ]


def _make_workflow(
    chart_builder=None, enable_visualization=True
) -> ExcelAnalysisWorkflow:
    return ExcelAnalysisWorkflow(
        excel_parser=MagicMock(),
        claude_client=MagicMock(),
        tavily_search=MagicMock(),
        hallucination_evaluator=MagicMock(),
        search_decision=MagicMock(),
        logger=MagicMock(),
        retry_policy=AnalysisRetryPolicy(max_retries=3),
        quality_threshold=AnalysisQualityThreshold(),
        chart_builder=chart_builder,
        enable_visualization=enable_visualization,
    )


def _nodes(wf: ExcelAnalysisWorkflow) -> set[str]:
    return set(wf._graph.get_graph().nodes.keys())


class TestExcelChartBuilderWiring:
    def test_chart_builder_node_present_when_injected(self):
        wf = _make_workflow(chart_builder=_FakeBuilder())
        nodes = _nodes(wf)
        assert "chart_router" in nodes
        assert "chart_builder" in nodes

    def test_chart_builder_node_absent_when_none(self):
        wf = _make_workflow(chart_builder=None)
        nodes = _nodes(wf)
        assert "chart_router" in nodes
        assert "chart_builder" not in nodes


class TestExcelVisualizationDisabled:
    """excel-chart-routing-dedup: Supervisor 재사용 인스턴스(차트 OFF) 검증.

    시각화는 상위 Supervisor chart_router/chart_builder가 전담하므로,
    enable_visualization=False면 내부 차트 서브그래프를 아예 등록하지 않고
    evaluate_hallucination 완료 시 바로 END로 종료한다(중복 제거).
    """

    def test_chart_nodes_absent_when_visualization_disabled(self):
        wf = _make_workflow(chart_builder=_FakeBuilder(), enable_visualization=False)
        nodes = _nodes(wf)
        assert "chart_router" not in nodes
        assert "chart_builder" not in nodes

    def test_evaluate_completes_directly_to_end(self):
        wf = _make_workflow(chart_builder=None, enable_visualization=False)
        # complete 분기 목적지가 차트 노드가 아닌 END여야 한다.
        # evaluate_hallucination 의 후속 노드 집합에 chart_router 가 없어야 함.
        graph = wf._graph.get_graph()
        successors = {
            e.target for e in graph.edges if e.source == "evaluate_hallucination"
        }
        assert "chart_router" not in successors
