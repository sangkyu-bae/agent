"""retrieval-observability §6-4/5/6: tool의 record_retrieval 쿼리 컨텍스트 전달.

Design §4.2 — 단일 검색(query_source=original), multi_query(hit별 태깅 D6),
routed(search_mode=routed, 개별 점수 NULL D7).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.application.agent_run.context import (
    RunContext,
    reset_run_context,
    set_current_run_context,
)
from src.application.rag_agent.tools import InternalDocumentSearchTool
from src.domain.agent_run.auth_context import AuthContext
from src.domain.agent_run.value_objects import RunId
from src.domain.hybrid_search.schemas import HybridSearchResponse, HybridSearchResult
from src.domain.multi_query.schemas import MultiQueryResult, PerQueryHits


def _hit(hit_id: str, score: float = 0.9) -> HybridSearchResult:
    return HybridSearchResult(
        id=hit_id,
        content=f"내용 {hit_id}",
        score=score,
        bm25_rank=1,
        bm25_score=5.5,
        vector_rank=2,
        vector_score=0.88,
        source="both",
        metadata={"source": "doc.pdf", "document_id": "doc-1"},
    )


def _admin_ctx() -> AuthContext:
    return AuthContext(
        user_id=1, display_name="admin", role="admin",
        primary_department_id="dept-001",
        primary_department_name="DX팀",
        department_ids=("dept-001",),
        department_names=("DX팀",),
        permissions=frozenset({
            "USE_RAG_SEARCH", "READ_DEPARTMENT_DOCS", "READ_PUBLIC_DOCS",
        }),
    )


def _make_tracker() -> MagicMock:
    tracker = MagicMock()
    tracker.record_retrieval = AsyncMock(return_value=None)
    return tracker


def _push_run_context():
    return set_current_run_context(
        RunContext(
            run_id=RunId("11111111-1111-1111-1111-111111111111"),
            user_id="user-1",
            agent_id="agent-1",
            callback=MagicMock(),
            tool_call_id="tc-1",
        )
    )


def _make_tool(**kwargs) -> InternalDocumentSearchTool:
    defaults = {
        "hybrid_search_use_case": MagicMock(),
        "request_id": "req-001",
        "collection_name": "finance-docs",
        "top_k": 5,
        "auth_ctx": _admin_ctx(),
    }
    defaults.update(kwargs)
    return InternalDocumentSearchTool(**defaults)


class TestSingleQueryContext:
    """§6-4: 단일 검색 — search_query=tool 입력, query_source=original, 개별 점수."""

    @pytest.mark.asyncio
    async def test_single_search_records_query_context(self) -> None:
        tracker = _make_tracker()
        hybrid = MagicMock()
        hybrid.execute = AsyncMock(
            return_value=HybridSearchResponse(
                query="질문", results=[_hit("c1")], total_found=1,
                request_id="req-001",
            )
        )
        tool = _make_tool(hybrid_search_use_case=hybrid, tracker=tracker)
        token = _push_run_context()
        try:
            await tool._arun("검색 질문")
        finally:
            reset_run_context(token)

        kwargs = tracker.record_retrieval.await_args_list[0].kwargs
        assert kwargs["search_query"] == "검색 질문"
        assert kwargs["query_source"] == "original"
        assert kwargs["search_mode"] == "hybrid"
        assert kwargs["bm25_score"] == pytest.approx(5.5)
        assert kwargs["vector_score"] == pytest.approx(0.88)
        assert kwargs["bm25_rank"] == 1
        assert kwargs["vector_rank"] == 2
        assert kwargs["fusion_source"] == "both"

    @pytest.mark.asyncio
    async def test_search_mode_field_propagated(self) -> None:
        """search_mode=vector_only 설정 시 그대로 기록."""
        tracker = _make_tracker()
        hybrid = MagicMock()
        hybrid.execute = AsyncMock(
            return_value=HybridSearchResponse(
                query="질문", results=[_hit("c1")], total_found=1,
                request_id="req-001",
            )
        )
        tool = _make_tool(
            hybrid_search_use_case=hybrid, tracker=tracker,
            search_mode="vector_only",
        )
        token = _push_run_context()
        try:
            await tool._arun("질문")
        finally:
            reset_run_context(token)

        kwargs = tracker.record_retrieval.await_args_list[0].kwargs
        assert kwargs["search_mode"] == "vector_only"


class TestMultiQueryContext:
    """§6-5 (D6): hit별 matched_queries 태깅 + 대표 쿼리."""

    @pytest.mark.asyncio
    async def test_multi_query_tags_hits_with_contributing_queries(self) -> None:
        tracker = _make_tracker()
        mq = MagicMock()
        mq.execute = AsyncMock(
            return_value=MultiQueryResult(
                original_query="원 질문",
                query_type="complex",
                generated_queries=["쿼리A", "쿼리B"],
                results=[_hit("c1"), _hit("c2")],
                total_found=2,
                request_id="req-001",
                per_query_hits=[
                    PerQueryHits(query="쿼리A", hit_ids=["c1", "c2"]),
                    PerQueryHits(query="쿼리B", hit_ids=["c2"]),
                ],
            )
        )
        tool = _make_tool(
            tracker=tracker, multi_query_use_case=mq, use_multi_query=True,
        )
        token = _push_run_context()
        try:
            await tool._arun("원 질문")
        finally:
            reset_run_context(token)

        assert tracker.record_retrieval.await_count == 2
        c1 = tracker.record_retrieval.await_args_list[0].kwargs
        assert c1["search_query"] == "쿼리A"
        assert c1["query_source"] == "multi_query"
        assert c1["search_mode"] == "hybrid"
        assert c1["metadata"]["matched_queries"] == ["쿼리A"]
        assert c1["metadata"]["generated_queries"] == ["쿼리A", "쿼리B"]

        c2 = tracker.record_retrieval.await_args_list[1].kwargs
        assert c2["search_query"] == "쿼리A"  # 첫 기여 쿼리 대표
        assert c2["metadata"]["matched_queries"] == ["쿼리A", "쿼리B"]

    @pytest.mark.asyncio
    async def test_multi_query_without_per_query_hits_falls_back(self) -> None:
        """per_query_hits=None(구버전 응답)이면 원 tool 입력으로 기록."""
        tracker = _make_tracker()
        mq = MagicMock()
        mq.execute = AsyncMock(
            return_value=MultiQueryResult(
                original_query="원 질문",
                query_type="simple",
                generated_queries=["재작성"],
                results=[_hit("c1")],
                total_found=1,
                request_id="req-001",
            )
        )
        tool = _make_tool(
            tracker=tracker, multi_query_use_case=mq, use_multi_query=True,
        )
        token = _push_run_context()
        try:
            await tool._arun("원 질문")
        finally:
            reset_run_context(token)

        kwargs = tracker.record_retrieval.await_args_list[0].kwargs
        assert kwargs["search_query"] == "원 질문"
        assert kwargs["query_source"] == "multi_query"


class TestRoutedContext:
    """§6-6 (D7): routed — search_mode=routed, 개별 점수 NULL."""

    @pytest.mark.asyncio
    async def test_routed_records_mode_and_query(self) -> None:
        from src.domain.routed_retrieval.schemas import RoutedChunk

        tracker = _make_tracker()
        chunk = RoutedChunk(
            content="라우팅 결과",
            section_ref="sec-1",
            document_id="doc-1",
            score=0.05,
            from_fallback=True,
            clause_title="제1조",
        )
        routed_result = MagicMock()
        routed_result.results = [chunk]
        routed_result.fallback_count = 1
        routed_result.fallback_used = True
        routed_uc = MagicMock()
        routed_uc.execute = AsyncMock(return_value=routed_result)

        tool = _make_tool(
            tracker=tracker,
            use_routed_search=True,
            routed_retrieval_getter=lambda: routed_uc,
        )
        token = _push_run_context()
        try:
            await tool._arun("라우팅 질문")
        finally:
            reset_run_context(token)

        kwargs = tracker.record_retrieval.await_args_list[0].kwargs
        assert kwargs["search_query"] == "라우팅 질문"
        assert kwargs["query_source"] == "original"
        assert kwargs["search_mode"] == "routed"
        assert kwargs.get("bm25_score") is None
        assert kwargs.get("vector_score") is None
