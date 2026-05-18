"""Tests for MultiQueryRewriteWorkflow."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.domain.hybrid_search.schemas import (
    HybridSearchRequest,
    HybridSearchResponse,
    HybridSearchResult,
)
from src.domain.query_rewrite.value_objects import RewrittenQuery


def make_search_response(query: str, doc_ids: list[str]) -> HybridSearchResponse:
    results = [
        HybridSearchResult(
            id=doc_id,
            content=f"content of {doc_id}",
            score=0.5,
            bm25_rank=i + 1,
            bm25_score=5.0,
            vector_rank=i + 1,
            vector_score=0.8,
            source="both",
            metadata={},
        )
        for i, doc_id in enumerate(doc_ids)
    ]
    return HybridSearchResponse(
        query=query, results=results, total_found=len(results), request_id="req-test"
    )


@pytest.fixture
def mock_logger():
    logger = MagicMock()
    logger.info = MagicMock()
    logger.error = MagicMock()
    logger.warning = MagicMock()
    return logger


@pytest.fixture
def mock_query_generator():
    gen = AsyncMock()
    gen.generate = AsyncMock(return_value=["변형1", "변형2", "변형3"])
    return gen


@pytest.fixture
def mock_hybrid_search():
    uc = AsyncMock()
    uc.execute = AsyncMock(
        return_value=make_search_response("test", ["doc-1", "doc-2"])
    )
    return uc


@pytest.fixture
def mock_query_rewriter():
    rw = AsyncMock()
    rw.rewrite = AsyncMock(
        return_value=RewrittenQuery(
            original_query="금리", rewritten_query="기준금리 정책 현황"
        )
    )
    return rw


class TestMultiQueryRewriteWorkflow:
    """LangGraph Multi-Query 워크플로우 테스트."""

    @pytest.mark.asyncio
    async def test_simple_query_uses_rewriter(
        self, mock_logger, mock_query_generator, mock_hybrid_search, mock_query_rewriter
    ) -> None:
        """simple 쿼리는 기존 QueryRewriter를 사용."""
        from src.application.multi_query.workflow import MultiQueryRewriteWorkflow

        workflow = MultiQueryRewriteWorkflow(
            query_generator=mock_query_generator,
            hybrid_search=mock_hybrid_search,
            query_rewriter=mock_query_rewriter,
            logger=mock_logger,
        )

        result = await workflow.run(
            query="2024년 한국은행 기준금리 인상 정책에 대해 알려주세요",
            request_id="req-simple",
            top_k=5,
        )

        assert result["query_type"] == "simple"
        assert result["status"] == "completed"
        assert len(result["fused_results"]) > 0
        mock_query_generator.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_complex_query_generates_multi_queries(
        self, mock_logger, mock_query_generator, mock_hybrid_search, mock_query_rewriter
    ) -> None:
        """complex 쿼리는 Multi-Query를 생성."""
        from src.application.multi_query.workflow import MultiQueryRewriteWorkflow

        workflow = MultiQueryRewriteWorkflow(
            query_generator=mock_query_generator,
            hybrid_search=mock_hybrid_search,
            query_rewriter=mock_query_rewriter,
            logger=mock_logger,
        )

        result = await workflow.run(
            query="정기예금과 정기적금의 금리 비교",
            request_id="req-complex",
            top_k=5,
        )

        assert result["query_type"] == "complex"
        assert result["status"] == "completed"
        assert len(result["generated_queries"]) == 3
        mock_query_generator.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_ambiguous_query_generates_multi_queries(
        self, mock_logger, mock_query_generator, mock_hybrid_search, mock_query_rewriter
    ) -> None:
        """ambiguous 쿼리도 Multi-Query를 생성."""
        from src.application.multi_query.workflow import MultiQueryRewriteWorkflow

        workflow = MultiQueryRewriteWorkflow(
            query_generator=mock_query_generator,
            hybrid_search=mock_hybrid_search,
            query_rewriter=mock_query_rewriter,
            logger=mock_logger,
        )

        result = await workflow.run(
            query="적금 금리",
            request_id="req-ambiguous",
            top_k=5,
        )

        assert result["query_type"] == "ambiguous"
        assert result["status"] == "completed"
        mock_query_generator.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_original(
        self, mock_logger, mock_hybrid_search, mock_query_rewriter
    ) -> None:
        """LLM 실패 시 원본 쿼리로 fallback 검색."""
        from src.application.multi_query.workflow import MultiQueryRewriteWorkflow

        failing_generator = AsyncMock()
        failing_generator.generate = AsyncMock(return_value=["적금 금리"])

        workflow = MultiQueryRewriteWorkflow(
            query_generator=failing_generator,
            hybrid_search=mock_hybrid_search,
            query_rewriter=mock_query_rewriter,
            logger=mock_logger,
        )

        result = await workflow.run(
            query="적금 금리",
            request_id="req-fallback",
            top_k=5,
        )

        assert result["status"] == "completed"
        assert len(result["fused_results"]) > 0

    @pytest.mark.asyncio
    async def test_parallel_search_called_per_query(
        self, mock_logger, mock_query_generator, mock_query_rewriter
    ) -> None:
        """각 변형 쿼리마다 HybridSearch가 호출된다."""
        from src.application.multi_query.workflow import MultiQueryRewriteWorkflow

        mock_hs = AsyncMock()
        mock_hs.execute = AsyncMock(
            return_value=make_search_response("q", ["doc-1"])
        )

        workflow = MultiQueryRewriteWorkflow(
            query_generator=mock_query_generator,
            hybrid_search=mock_hs,
            query_rewriter=mock_query_rewriter,
            logger=mock_logger,
        )

        result = await workflow.run(
            query="적금 금리",
            request_id="req-parallel",
            top_k=5,
        )

        assert mock_hs.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_fused_results_dedup_across_queries(
        self, mock_logger, mock_query_generator, mock_query_rewriter
    ) -> None:
        """여러 쿼리에서 동일 문서가 나오면 중복 제거 + 점수 누적."""
        from src.application.multi_query.workflow import MultiQueryRewriteWorkflow

        mock_hs = AsyncMock()
        mock_hs.execute = AsyncMock(
            return_value=make_search_response("q", ["shared-doc", "unique"])
        )

        workflow = MultiQueryRewriteWorkflow(
            query_generator=mock_query_generator,
            hybrid_search=mock_hs,
            query_rewriter=mock_query_rewriter,
            logger=mock_logger,
        )

        result = await workflow.run(
            query="적금 금리",
            request_id="req-dedup",
            top_k=10,
        )

        ids = [r.id for r in result["fused_results"]]
        assert ids.count("shared-doc") == 1
        shared = next(r for r in result["fused_results"] if r.id == "shared-doc")
        unique = next(r for r in result["fused_results"] if r.id == "unique")
        assert shared.score > unique.score


class TestMultiQuerySearchUseCase:
    """MultiQuerySearchUseCase 테스트."""

    @pytest.mark.asyncio
    async def test_execute_returns_multi_query_result(
        self, mock_logger, mock_query_generator, mock_hybrid_search, mock_query_rewriter
    ) -> None:
        """execute()는 MultiQueryResult를 반환."""
        from src.application.multi_query.use_case import MultiQuerySearchUseCase
        from src.domain.multi_query.schemas import MultiQueryResult

        use_case = MultiQuerySearchUseCase(
            query_generator=mock_query_generator,
            hybrid_search=mock_hybrid_search,
            query_rewriter=mock_query_rewriter,
            logger=mock_logger,
        )

        result = await use_case.execute(
            query="적금 금리",
            request_id="req-uc",
            top_k=5,
        )

        assert isinstance(result, MultiQueryResult)
        assert result.original_query == "적금 금리"
        assert result.request_id == "req-uc"

    @pytest.mark.asyncio
    async def test_execute_passes_collection_and_index(
        self, mock_logger, mock_query_generator, mock_query_rewriter
    ) -> None:
        """collection_name과 es_index가 HybridSearch에 전달된다."""
        from src.application.multi_query.use_case import MultiQuerySearchUseCase

        mock_hs = AsyncMock()
        mock_hs.execute = AsyncMock(
            return_value=make_search_response("q", ["doc-1"])
        )

        use_case = MultiQuerySearchUseCase(
            query_generator=mock_query_generator,
            hybrid_search=mock_hs,
            query_rewriter=mock_query_rewriter,
            logger=mock_logger,
        )

        await use_case.execute(
            query="적금 금리",
            request_id="req-uc2",
            top_k=5,
            collection_name="my-collection",
            es_index="my-index",
        )

        call_args = mock_hs.execute.call_args_list[0]
        request = call_args[0][0]
        assert request.collection_name == "my-collection"
        assert request.es_index == "my-index"
