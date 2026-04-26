"""InternalDocumentSearchTool 단위 테스트 — search_mode 분기 검증."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.application.rag_agent.tools import InternalDocumentSearchTool
from src.domain.hybrid_search.schemas import HybridSearchResponse, HybridSearchResult


def _make_response(query: str = "q") -> HybridSearchResponse:
    return HybridSearchResponse(
        query=query,
        results=[
            HybridSearchResult(
                id="doc-1",
                content="결과 내용",
                score=0.9,
                bm25_rank=1,
                bm25_score=5.0,
                vector_rank=1,
                vector_score=0.9,
                source="both",
                metadata={"source": "test.pdf"},
            )
        ],
        total_found=1,
        request_id="req-001",
    )


def _make_tool(**kwargs) -> InternalDocumentSearchTool:
    mock_use_case = MagicMock()
    mock_use_case.execute = AsyncMock(return_value=_make_response())
    defaults = {
        "hybrid_search_use_case": mock_use_case,
        "request_id": "req-001",
    }
    defaults.update(kwargs)
    return InternalDocumentSearchTool(**defaults)


class TestSearchModeBranching:
    @pytest.mark.asyncio
    async def test_hybrid_mode_calls_use_case_execute(self):
        tool = _make_tool(search_mode="hybrid")
        await tool._arun("테스트 질문")
        tool.hybrid_search_use_case.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_vector_only_mode_skips_bm25(self):
        """vector_only 모드에서는 bm25_top_k=0으로 BM25 검색 비활성."""
        tool = _make_tool(search_mode="vector_only", top_k=5)
        await tool._arun("벡터 전용 검색")

        call_args = tool.hybrid_search_use_case.execute.call_args
        request = call_args[0][0]
        assert request.bm25_top_k == 0
        assert request.vector_top_k == 5 * 2

    @pytest.mark.asyncio
    async def test_bm25_only_mode_skips_vector(self):
        """bm25_only 모드에서는 vector_top_k=0으로 벡터 검색 비활성."""
        tool = _make_tool(search_mode="bm25_only", top_k=5)
        await tool._arun("BM25 전용 검색")

        call_args = tool.hybrid_search_use_case.execute.call_args
        request = call_args[0][0]
        assert request.vector_top_k == 0
        assert request.bm25_top_k == 5 * 2

    @pytest.mark.asyncio
    async def test_default_mode_is_hybrid(self):
        tool = _make_tool()
        assert tool.search_mode == "hybrid"

    @pytest.mark.asyncio
    async def test_metadata_filter_passed_in_all_modes(self):
        for mode in ("hybrid", "vector_only", "bm25_only"):
            tool = _make_tool(
                search_mode=mode,
                metadata_filter={"dept": "finance"},
            )
            await tool._arun("필터 테스트")

            call_args = tool.hybrid_search_use_case.execute.call_args
            request = call_args[0][0]
            assert request.metadata_filter == {"dept": "finance"}

    @pytest.mark.asyncio
    async def test_no_results_returns_fallback_message(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            return_value=HybridSearchResponse(
                query="q", results=[], total_found=0, request_id="req"
            )
        )
        tool = _make_tool(hybrid_search_use_case=mock_uc)
        result = await tool._arun("결과 없음")
        assert "찾지 못했습니다" in result
