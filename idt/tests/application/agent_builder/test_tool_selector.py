"""ToolSelector 단위 테스트."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.tool_selector import ToolSelector, _SkeletonOutput, _WorkerOutput
from src.domain.agent_builder.schemas import WorkflowSkeleton


def _make_skeleton_output() -> _SkeletonOutput:
    return _SkeletonOutput(
        workers=[
            _WorkerOutput(
                tool_id="tavily_search",
                worker_id="search_worker",
                description="Tavily로 AI 뉴스 검색",
                sort_order=0,
            ),
            _WorkerOutput(
                tool_id="excel_export",
                worker_id="export_worker",
                description="검색 결과를 엑셀로 저장",
                sort_order=1,
            ),
        ],
        flow_hint="search_worker 먼저 실행 후 export_worker 실행",
    )


def _make_selector() -> ToolSelector:
    mock_llm = MagicMock()
    mock_llm.with_structured_output = MagicMock(return_value=mock_llm)
    mock_llm.ainvoke = AsyncMock(return_value=_make_skeleton_output())
    logger = MagicMock()
    return ToolSelector(llm=mock_llm, logger=logger), mock_llm


class TestToolSelector:
    @pytest.mark.asyncio
    async def test_select_returns_workflow_skeleton(self):
        selector, _ = _make_selector()
        result = await selector.select("AI 뉴스 검색하고 엑셀 저장", "req-1")
        assert isinstance(result, WorkflowSkeleton)

    @pytest.mark.asyncio
    async def test_select_workers_mapped_correctly(self):
        selector, _ = _make_selector()
        result = await selector.select("AI 뉴스 검색하고 엑셀 저장", "req-1")
        assert len(result.workers) == 2
        assert result.workers[0].tool_id == "tavily_search"
        assert result.workers[0].worker_id == "search_worker"
        assert result.workers[1].tool_id == "excel_export"

    @pytest.mark.asyncio
    async def test_select_flow_hint_included(self):
        selector, _ = _make_selector()
        result = await selector.select("AI 뉴스 검색하고 엑셀 저장", "req-1")
        assert "search_worker" in result.flow_hint

    @pytest.mark.asyncio
    async def test_select_calls_llm_with_tool_list(self):
        selector, mock_llm = _make_selector()
        await selector.select("AI 뉴스 검색하고 엑셀 저장", "req-1")
        mock_llm.ainvoke.assert_called_once()
        messages = mock_llm.ainvoke.call_args[0][0]
        system_msg = next(m for m in messages if m["role"] == "system")
        assert "tavily_search" in system_msg["content"]

    @pytest.mark.asyncio
    async def test_select_raises_on_llm_error(self):
        selector, mock_llm = _make_selector()
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM error"))
        with pytest.raises(RuntimeError, match="LLM error"):
            await selector.select("쿼리", "req-1")
