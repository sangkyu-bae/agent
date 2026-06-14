"""LangChainChartTransformer 테스트 (LLM은 AsyncMock).

chart-context-continuity Design §3.6: structured output + graceful degrade + 8KB 절단.
"""
from unittest.mock import AsyncMock, MagicMock

from src.domain.visualization.chart_policy import (
    ChartEditDraft,
    ChartEditDraftList,
    ChartEditSeriesDraft,
    ChartStylePolicy,
)
from src.domain.visualization.chart_schemas import ChartType
from src.infrastructure.visualization.llm_chart_transformer import (
    LangChainChartTransformer,
)


def _edit_draft(color: str | None = None) -> ChartEditDraft:
    return ChartEditDraft(
        chart_type=ChartType.BAR,
        title="t",
        labels=["a", "b", "c"],
        series=[ChartEditSeriesDraft(name="S", data=[1.0, 2.0, 3.0], color=color)],
    )


def _stored_chart(n_points: int = 3) -> dict:
    """conversation_message.charts에 저장된 JSON 형태."""
    return {
        "type": "bar",
        "data": {
            "labels": [f"L{i}" for i in range(n_points)],
            "datasets": [
                {"label": "건수", "data": [float(i) for i in range(n_points)]}
            ],
        },
        "options": {"responsive": True},
    }


def _llm_returning(draft_list: ChartEditDraftList) -> MagicMock:
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=draft_list)
    llm = MagicMock()
    llm.with_structured_output = MagicMock(return_value=structured)
    return llm


def _transformer(llm: MagicMock) -> LangChainChartTransformer:
    return LangChainChartTransformer(
        llm=llm, logger=MagicMock(), style_policy=ChartStylePolicy(),
    )


class TestTransform:
    async def test_transform_returns_styled_charts_and_message(self) -> None:
        llm = _llm_returning(
            ChartEditDraftList(charts=[_edit_draft()], message="색상을 적용했습니다.")
        )
        result = await _transformer(llm).transform("색 바꿔줘", [_stored_chart()])
        assert len(result.charts) == 1
        assert result.charts[0].data.datasets[0].backgroundColor is not None
        assert result.message == "색상을 적용했습니다."

    async def test_explicit_color_override_applied(self) -> None:
        llm = _llm_returning(
            ChartEditDraftList(charts=[_edit_draft(color="#FF0000")], message="ok")
        )
        result = await _transformer(llm).transform("빨간색으로", [_stored_chart()])
        assert result.charts[0].data.datasets[0].backgroundColor == "#FF0000"

    async def test_llm_exception_returns_empty_result(self) -> None:
        structured = MagicMock()
        structured.ainvoke = AsyncMock(side_effect=RuntimeError("boom"))
        llm = MagicMock()
        llm.with_structured_output = MagicMock(return_value=structured)
        result = await _transformer(llm).transform("색 바꿔줘", [_stored_chart()])
        assert result.charts == []

    async def test_uses_structured_output_with_edit_draft_list(self) -> None:
        llm = _llm_returning(ChartEditDraftList(charts=[_edit_draft()]))
        await _transformer(llm).transform("q", [_stored_chart()])
        llm.with_structured_output.assert_called_once_with(ChartEditDraftList)

    async def test_prompt_contains_instruction_charts_and_context(self) -> None:
        llm = _llm_returning(ChartEditDraftList(charts=[_edit_draft()]))
        structured = llm.with_structured_output.return_value
        await _transformer(llm).transform(
            "해당 그래프 색 바꿔줘", [_stored_chart()], context="분석 데이터 XYZ",
        )
        prompt = structured.ainvoke.call_args.args[0]
        assert "해당 그래프 색 바꿔줘" in prompt
        assert "L1" in prompt          # 기존 차트 직렬화 포함
        assert "XYZ" in prompt          # 보조 컨텍스트 포함

    async def test_oversized_charts_truncated(self) -> None:
        """직렬화 8KB 초과 시 dataset.data/labels 앞 100포인트로 절단."""
        llm = _llm_returning(ChartEditDraftList(charts=[_edit_draft()]))
        structured = llm.with_structured_output.return_value
        await _transformer(llm).transform("q", [_stored_chart(n_points=5000)])
        prompt = structured.ainvoke.call_args.args[0]
        assert "L99" in prompt          # 앞부분 유지
        assert "L4999" not in prompt    # 꼬리 절단
        assert len(prompt) < 20_000

    async def test_empty_drafts_filtered(self) -> None:
        empty = ChartEditDraft(chart_type=ChartType.BAR, labels=[], series=[])
        llm = _llm_returning(
            ChartEditDraftList(charts=[empty, _edit_draft()], message="m")
        )
        result = await _transformer(llm).transform("q", [_stored_chart()])
        assert len(result.charts) == 1
