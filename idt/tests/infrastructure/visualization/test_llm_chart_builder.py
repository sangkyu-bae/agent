"""LangChainChartBuilder 테스트 (LLM은 AsyncMock)."""
from unittest.mock import AsyncMock, MagicMock

from src.domain.visualization.chart_policy import (
    ChartDraft,
    ChartDraftList,
    ChartSeriesDraft,
    ChartStylePolicy,
)
from src.domain.visualization.chart_schemas import ChartType
from src.infrastructure.visualization.llm_chart_builder import LangChainChartBuilder


def _draft(chart_type: ChartType = ChartType.BAR, n: int = 3) -> ChartDraft:
    return ChartDraft(
        chart_type=chart_type,
        title="t",
        labels=[f"L{i}" for i in range(n)],
        series=[ChartSeriesDraft(name="S", data=[float(i) for i in range(n)])],
    )


def _llm_returning(draft_list: ChartDraftList) -> MagicMock:
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=draft_list)
    llm = MagicMock()
    llm.with_structured_output = MagicMock(return_value=structured)
    return llm


def _builder(llm: MagicMock, max_count: int = 3) -> LangChainChartBuilder:
    return LangChainChartBuilder(
        llm=llm, logger=MagicMock(),
        style_policy=ChartStylePolicy(), max_count=max_count,
    )


class TestBuild:
    async def test_single_chart_with_colors_and_options(self) -> None:
        llm = _llm_returning(ChartDraftList(charts=[_draft()]))
        result = await _builder(llm).build("그래프 그려줘", "1 2 3")
        assert len(result) == 1
        ds = result[0].data.datasets[0]
        assert ds.backgroundColor is not None       # 색상 채워짐
        assert result[0].options is not None          # options 채워짐

    async def test_caps_to_max_count(self) -> None:
        llm = _llm_returning(ChartDraftList(charts=[_draft() for _ in range(5)]))
        result = await _builder(llm, max_count=3).build("q", "a")
        assert len(result) == 3

    async def test_drops_draft_with_empty_labels_or_series(self) -> None:
        empty = ChartDraft(chart_type=ChartType.BAR, labels=[], series=[])
        llm = _llm_returning(ChartDraftList(charts=[empty, _draft()]))
        result = await _builder(llm).build("q", "a")
        assert len(result) == 1

    async def test_llm_exception_returns_empty(self) -> None:
        structured = MagicMock()
        structured.ainvoke = AsyncMock(side_effect=RuntimeError("boom"))
        llm = MagicMock()
        llm.with_structured_output = MagicMock(return_value=structured)
        result = await _builder(llm).build("q", "a")
        assert result == []

    async def test_uses_structured_output_with_draft_list(self) -> None:
        llm = _llm_returning(ChartDraftList(charts=[_draft()]))
        await _builder(llm).build("q", "a")
        llm.with_structured_output.assert_called_once_with(ChartDraftList)

    async def test_context_included_in_prompt(self) -> None:
        llm = _llm_returning(ChartDraftList(charts=[_draft()]))
        structured = llm.with_structured_output.return_value
        await _builder(llm).build("q", "answer", context="출처 컨텍스트 XYZ")
        prompt = structured.ainvoke.call_args.args[0]
        assert "XYZ" in prompt
