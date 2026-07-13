"""retrieval-observability §6-3: MultiQueryResult.per_query_hits.

Design §4.3 — 재작성 쿼리별 hit id 목록 노출 (additive, 기본 None 하위호환).
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.multi_query.use_case import MultiQuerySearchUseCase
from src.domain.hybrid_search.schemas import HybridSearchResult
from src.domain.multi_query.schemas import MultiQueryResult, PerQueryHits


def _hit(hit_id: str, score: float = 0.9) -> HybridSearchResult:
    return HybridSearchResult(
        id=hit_id,
        content=f"내용 {hit_id}",
        score=score,
        bm25_rank=1,
        bm25_score=5.0,
        vector_rank=1,
        vector_score=0.9,
        source="both",
        metadata={"source": "doc.pdf"},
    )


class TestPerQueryHitsSchema:
    def test_per_query_hits_default_none(self) -> None:
        """기존 생성 시그니처 하위호환 — per_query_hits 미전달 시 None."""
        result = MultiQueryResult(
            original_query="원 질문",
            query_type="simple",
            generated_queries=["재작성"],
            results=[],
            total_found=0,
            request_id="req-1",
        )
        assert result.per_query_hits is None

    def test_per_query_hits_holds_query_and_ids(self) -> None:
        pq = PerQueryHits(query="재작성 쿼리", hit_ids=["c1", "c2"])
        assert pq.query == "재작성 쿼리"
        assert pq.hit_ids == ["c1", "c2"]


class TestUseCaseFillsPerQueryHits:
    @pytest.mark.asyncio
    async def test_execute_zips_queries_with_per_query_results(self) -> None:
        """workflow state의 generated_queries × per_query_results를 zip해 채움."""
        use_case = MultiQuerySearchUseCase(
            query_generator=MagicMock(),
            hybrid_search=MagicMock(),
            query_rewriter=MagicMock(),
            logger=MagicMock(),
        )
        state = {
            "query_type": "complex",
            "generated_queries": ["쿼리A", "쿼리B"],
            "per_query_results": [
                [_hit("c1"), _hit("c2")],
                [_hit("c2"), _hit("c3")],
            ],
            "fused_results": [_hit("c2"), _hit("c1"), _hit("c3")],
        }
        workflow = MagicMock()
        workflow.run = AsyncMock(return_value=state)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "src.application.multi_query.use_case.MultiQueryRewriteWorkflow",
                MagicMock(return_value=workflow),
            )
            result = await use_case.execute(query="원 질문", request_id="req-1")

        assert result.per_query_hits is not None
        assert len(result.per_query_hits) == 2
        assert result.per_query_hits[0].query == "쿼리A"
        assert result.per_query_hits[0].hit_ids == ["c1", "c2"]
        assert result.per_query_hits[1].query == "쿼리B"
        assert result.per_query_hits[1].hit_ids == ["c2", "c3"]

    @pytest.mark.asyncio
    async def test_execute_handles_length_mismatch_gracefully(self) -> None:
        """zip은 짧은 쪽 기준 — 실패 폴백 state(빈 per_query_results)에서도 안전."""
        use_case = MultiQuerySearchUseCase(
            query_generator=MagicMock(),
            hybrid_search=MagicMock(),
            query_rewriter=MagicMock(),
            logger=MagicMock(),
        )
        state = {
            "query_type": "simple",
            "generated_queries": ["쿼리A"],
            "per_query_results": [],
            "fused_results": [],
        }
        workflow = MagicMock()
        workflow.run = AsyncMock(return_value=state)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "src.application.multi_query.use_case.MultiQueryRewriteWorkflow",
                MagicMock(return_value=workflow),
            )
            result = await use_case.execute(query="원 질문", request_id="req-1")

        assert result.per_query_hits == []
