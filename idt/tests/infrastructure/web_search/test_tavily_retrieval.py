"""M5-1: TavilySearchTool retrieval 영속화 wiring 단위 테스트.

agent-run-observability-m5 Design §3.4, §9.1.
M4 InternalDocumentSearchTool과 동일 패턴 (collection_name='tavily_web').
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.agent_run.context import (
    RunContext,
    reset_run_context,
    set_current_run_context,
)
from src.domain.agent_run.value_objects import RunId
from src.domain.web_search.value_objects import SearchResult, SearchResultItem
from src.infrastructure.web_search.tavily_tool import TavilySearchTool


def _make_search_result() -> SearchResult:
    return SearchResult(
        query="LangChain",
        items=[
            SearchResultItem(
                title="LangChain Docs",
                url="https://python.langchain.com/docs/get_started",
                content="LangChain is a framework for LLM apps." * 20,
                score=0.95,
            ),
            SearchResultItem(
                title="LangChain GitHub",
                url="https://github.com/langchain-ai/langchain",
                content="Source code repository for LangChain.",
                score=0.88,
            ),
        ],
    )


def _make_tracker() -> MagicMock:
    tracker = MagicMock()
    tracker.record_retrieval = AsyncMock(return_value=None)
    return tracker


def _make_tool(tracker=None, logger=None) -> TavilySearchTool:
    with patch.dict("os.environ", {"TAVILY_API_KEY": "test-key"}):
        tool = TavilySearchTool(
            api_key="test-key",
            tracker=tracker,
            logger=logger,
        )
    return tool


def _push_run_context(
    run_id_value: str = "11111111-1111-1111-1111-111111111111",
    tool_call_id: str | None = "tc-tav-1",
):
    callback = MagicMock()
    ctx = RunContext(
        run_id=RunId(run_id_value),
        user_id="user-1",
        agent_id="agent-1",
        callback=callback,
        step_id="step-1",
        tool_call_id=tool_call_id,
    )
    return set_current_run_context(ctx)


class TestRecordRetrievalPerHit:
    @pytest.mark.asyncio
    async def test_arun_records_retrieval_per_item_with_rank_and_collection(self):
        tracker = _make_tracker()
        tool = _make_tool(tracker=tracker)

        token = _push_run_context()
        try:
            with patch.object(
                TavilySearchTool,
                "search_as_value_object",
                return_value=_make_search_result(),
            ):
                output = await tool._arun("LangChain")
        finally:
            reset_run_context(token)

        # 2 items → 2 record_retrieval calls
        assert tracker.record_retrieval.await_count == 2
        first = tracker.record_retrieval.await_args_list[0].kwargs
        assert first["collection_name"] == "tavily_web"
        assert first["chunk_id"] is None
        assert first["rank_index"] == 1
        assert first["score"] == pytest.approx(0.95)
        assert first["document_id"] == "https://python.langchain.com/docs/get_started"
        assert first["tool_call_id"] == "tc-tav-1"
        assert first["run_id"].value == "11111111-1111-1111-1111-111111111111"
        # metadata preserves full URL + title
        meta = first["metadata"]
        assert meta["url_full"] == "https://python.langchain.com/docs/get_started"
        assert meta["title"] == "LangChain Docs"

        second = tracker.record_retrieval.await_args_list[1].kwargs
        assert second["rank_index"] == 2

        # Tool still returns formatted XML output
        assert output is not None


class TestContextNoneSkip:
    @pytest.mark.asyncio
    async def test_arun_skips_retrieval_when_runcontext_none(self):
        tracker = _make_tracker()
        tool = _make_tool(tracker=tracker)

        # No context set
        with patch.object(
            TavilySearchTool,
            "search_as_value_object",
            return_value=_make_search_result(),
        ):
            output = await tool._arun("query")

        tracker.record_retrieval.assert_not_awaited()
        # Still returns formatted output
        assert output is not None

    @pytest.mark.asyncio
    async def test_arun_skips_retrieval_when_tracker_none(self):
        tool = _make_tool(tracker=None)

        token = _push_run_context()
        try:
            with patch.object(
                TavilySearchTool,
                "search_as_value_object",
                return_value=_make_search_result(),
            ):
                output = await tool._arun("query")
        finally:
            reset_run_context(token)

        # Tool still works without tracker
        assert output is not None


class TestToolCallIdFromContext:
    @pytest.mark.asyncio
    async def test_record_retrieval_forwards_tool_call_id_from_context(self):
        tracker = _make_tracker()
        tool = _make_tool(tracker=tracker)

        token = _push_run_context(tool_call_id="tc-xyz-999")
        try:
            with patch.object(
                TavilySearchTool,
                "search_as_value_object",
                return_value=_make_search_result(),
            ):
                await tool._arun("query")
        finally:
            reset_run_context(token)

        for call in tracker.record_retrieval.await_args_list:
            assert call.kwargs["tool_call_id"] == "tc-xyz-999"


class TestBestEffortIsolation:
    """★ 회귀 가드: record_retrieval 실패가 Tavily 답변 차단 안함."""

    @pytest.mark.asyncio
    async def test_record_retrieval_failure_does_not_break_tavily_output(self):
        tracker = _make_tracker()
        tracker.record_retrieval = AsyncMock(side_effect=RuntimeError("DB down"))
        logger = MagicMock()

        tool = _make_tool(tracker=tracker, logger=logger)

        token = _push_run_context()
        try:
            with patch.object(
                TavilySearchTool,
                "search_as_value_object",
                return_value=_make_search_result(),
            ):
                output = await tool._arun("query")
        finally:
            reset_run_context(token)

        # Tool returns formatted output despite all retrievals failing
        assert output is not None
        # Warning logged for failures
        assert logger.warning.called
