"""M4-1: InternalDocumentSearchTool retrieval 영속화 wiring 단위 테스트.

agent-run-observability-m4 Design §3.5, §9.1 — best-effort record_retrieval 호출 검증.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.application.rag_agent.tools import InternalDocumentSearchTool
from src.application.agent_run.context import (
    RunContext,
    reset_run_context,
    set_current_run_context,
)
from src.domain.agent_run.value_objects import RunId
from src.domain.hybrid_search.schemas import HybridSearchResponse, HybridSearchResult


def _make_results() -> list[HybridSearchResult]:
    return [
        HybridSearchResult(
            id="chunk-1",
            content="첫 번째 결과 내용입니다." * 30,
            score=0.92,
            bm25_rank=1,
            bm25_score=5.5,
            vector_rank=1,
            vector_score=0.9,
            source="both",
            metadata={"source": "doc1.pdf", "document_id": "doc-uuid-1"},
        ),
        HybridSearchResult(
            id="chunk-2",
            content="두 번째 결과 내용",
            score=0.85,
            bm25_rank=2,
            bm25_score=4.5,
            vector_rank=2,
            vector_score=0.85,
            source="both",
            metadata={"source": "doc2.pdf", "document_id": "doc-uuid-2"},
        ),
    ]


def _make_response() -> HybridSearchResponse:
    return HybridSearchResponse(
        query="질문",
        results=_make_results(),
        total_found=2,
        request_id="req-001",
    )


def _make_tracker() -> MagicMock:
    tracker = MagicMock()
    tracker.record_retrieval = AsyncMock(return_value=None)
    return tracker


def _make_tool(tracker=None, logger=None, **kwargs):
    # agent-user-context: 검색 동작 자체를 검증하는 테스트이므로 admin auth_ctx 주입.
    # Fail-Closed 디폴트(권한 없으면 거부)를 우회.
    from src.domain.agent_run.auth_context import AuthContext
    full_perm_ctx = AuthContext(
        user_id=1, display_name="admin", role="admin",
        primary_department_id="dept-001",
        primary_department_name="DX팀",
        department_ids=("dept-001",),
        department_names=("DX팀",),
        permissions=frozenset({
            "USE_RAG_SEARCH", "READ_DEPARTMENT_DOCS", "READ_PUBLIC_DOCS",
        }),
    )

    mock_use_case = MagicMock()
    mock_use_case.execute = AsyncMock(return_value=_make_response())
    defaults = {
        "hybrid_search_use_case": mock_use_case,
        "request_id": "req-001",
        "collection_name": "finance-docs",
        "top_k": 5,
        "auth_ctx": full_perm_ctx,
    }
    defaults.update(kwargs)
    tool = InternalDocumentSearchTool(**defaults)
    if tracker is not None:
        tool.tracker = tracker
    if logger is not None:
        tool.logger = logger
    return tool


def _push_run_context(
    run_id_value: str = "11111111-1111-1111-1111-111111111111",
    tool_call_id: str | None = "tc-1",
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
    """M4-1 FR-1: 검색 hit 각각에 대해 record_retrieval 호출."""

    @pytest.mark.asyncio
    async def test_format_results_records_retrieval_per_hit_with_rank_index(self):
        tracker = _make_tracker()
        tool = _make_tool(tracker=tracker)
        token = _push_run_context()
        try:
            await tool._arun("질문")
        finally:
            reset_run_context(token)

        assert tracker.record_retrieval.await_count == 2
        first_call = tracker.record_retrieval.await_args_list[0].kwargs
        assert first_call["chunk_id"] == "chunk-1"
        assert first_call["rank_index"] == 1
        assert first_call["score"] == pytest.approx(0.92)
        assert first_call["collection_name"] == "finance-docs"
        assert first_call["document_id"] == "doc-uuid-1"
        assert first_call["tool_call_id"] == "tc-1"
        assert first_call["run_id"].value == "11111111-1111-1111-1111-111111111111"

        second_call = tracker.record_retrieval.await_args_list[1].kwargs
        assert second_call["chunk_id"] == "chunk-2"
        assert second_call["rank_index"] == 2

    @pytest.mark.asyncio
    async def test_content_preview_truncated_to_500_chars(self):
        tracker = _make_tracker()
        tool = _make_tool(tracker=tracker)
        token = _push_run_context()
        try:
            await tool._arun("질문")
        finally:
            reset_run_context(token)

        first_call = tracker.record_retrieval.await_args_list[0].kwargs
        # default retrieval_preview_max_bytes = 500
        assert first_call["content_preview"] is not None
        assert len(first_call["content_preview"]) <= 500


class TestContextNoneSkip:
    """M4-1 FR-2: RunContext가 없으면 record_retrieval skip."""

    @pytest.mark.asyncio
    async def test_format_results_skips_retrieval_when_runcontext_none(self):
        tracker = _make_tracker()
        tool = _make_tool(tracker=tracker)
        # ContextVar 미세팅 — get_current_run_context() → None
        result = await tool._arun("질문")

        tracker.record_retrieval.assert_not_awaited()
        # 도구 출력은 정상 (영속화와 무관)
        assert "[출처: doc1.pdf]" in result

    @pytest.mark.asyncio
    async def test_format_results_skips_retrieval_when_tracker_none(self):
        # tracker 미주입 (도구 단독 사용 케이스)
        tool = _make_tool(tracker=None)
        token = _push_run_context()
        try:
            result = await tool._arun("질문")
        finally:
            reset_run_context(token)

        # 도구 출력은 정상
        assert "doc1.pdf" in result


class TestToolCallIdFromContext:
    """M4-1 FR-3: RunContext.tool_call_id가 record_retrieval에 그대로 전달."""

    @pytest.mark.asyncio
    async def test_record_retrieval_uses_tool_call_id_from_context(self):
        tracker = _make_tracker()
        tool = _make_tool(tracker=tracker)
        token = _push_run_context(tool_call_id="tc-xyz")
        try:
            await tool._arun("질문")
        finally:
            reset_run_context(token)

        for call in tracker.record_retrieval.await_args_list:
            assert call.kwargs["tool_call_id"] == "tc-xyz"

    @pytest.mark.asyncio
    async def test_tool_call_id_can_be_none_in_context(self):
        tracker = _make_tracker()
        tool = _make_tool(tracker=tracker)
        token = _push_run_context(tool_call_id=None)
        try:
            await tool._arun("질문")
        finally:
            reset_run_context(token)

        # tool_call_id None인 채로 record_retrieval 정상 호출 (M1 spec — Optional)
        assert tracker.record_retrieval.await_count == 2
        for call in tracker.record_retrieval.await_args_list:
            assert call.kwargs["tool_call_id"] is None


class TestBestEffortIsolation:
    """M4-1 FR-5 (★ 회귀 가드): record_retrieval 실패가 도구 응답을 깨지 않음."""

    @pytest.mark.asyncio
    async def test_record_retrieval_failure_does_not_break_tool_output(self):
        tracker = _make_tracker()
        tracker.record_retrieval = AsyncMock(side_effect=RuntimeError("DB down"))
        logger = MagicMock()

        tool = _make_tool(tracker=tracker, logger=logger)
        token = _push_run_context()
        try:
            result = await tool._arun("질문")
        finally:
            reset_run_context(token)

        # 도구 결과는 정상 반환
        assert "[출처: doc1.pdf]" in result
        assert "[출처: doc2.pdf]" in result
        # warning 로그 발생
        assert logger.warning.called

    @pytest.mark.asyncio
    async def test_partial_failure_continues_remaining_hits(self):
        """첫 hit record_retrieval 실패해도 두 번째 hit 정상 진행."""
        tracker = _make_tracker()
        # 첫 호출만 실패
        tracker.record_retrieval = AsyncMock(
            side_effect=[RuntimeError("boom"), None]
        )
        logger = MagicMock()

        tool = _make_tool(tracker=tracker, logger=logger)
        token = _push_run_context()
        try:
            result = await tool._arun("질문")
        finally:
            reset_run_context(token)

        assert tracker.record_retrieval.await_count == 2
        assert "[출처: doc2.pdf]" in result
