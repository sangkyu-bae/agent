"""RoutedRetrievalPolicy 테스트 (summary-routed-retrieval Design D8/D13)."""
import pytest

from src.domain.hybrid_search.schemas import HybridSearchResult
from src.domain.routed_retrieval.policy import RoutedRetrievalPolicy
from src.domain.routed_retrieval.schemas import RoutedChunk, RoutedParams


def _params(**overrides) -> RoutedParams:
    values = dict(
        doc_top_k=5, section_top_n=10, top_k=5,
        rrf_k=60, bm25_weight=0.5, vector_weight=0.5,
    )
    values.update(overrides)
    return RoutedParams(**values)


def _chunk(ref: str, score: float = 1.0) -> RoutedChunk:
    return RoutedChunk(
        section_ref=ref, document_id="doc-1", content=f"본문 {ref}", score=score
    )


def _fallback_hit(hit_id: str, chunk_id: str = "", parent_id: str = "") -> HybridSearchResult:
    metadata = {}
    if chunk_id:
        metadata["chunk_id"] = chunk_id
    if parent_id:
        metadata["parent_id"] = parent_id
    return HybridSearchResult(
        id=hit_id, content=f"fb {hit_id}", score=0.01,
        bm25_rank=1, bm25_score=1.0, vector_rank=None, vector_score=None,
        source="bm25_only", metadata=metadata,
    )


class TestValidateParams:
    def test_defaults_pass(self):
        RoutedRetrievalPolicy.validate_params(_params())

    @pytest.mark.parametrize(
        "overrides",
        [
            {"doc_top_k": 0}, {"doc_top_k": 21},
            {"section_top_n": 0}, {"section_top_n": 51},
            {"top_k": 0}, {"top_k": 31},
            {"rrf_k": 0},
            {"bm25_weight": -0.1}, {"vector_weight": 1.1},
        ],
    )
    def test_out_of_range_raises(self, overrides):
        with pytest.raises(ValueError):
            RoutedRetrievalPolicy.validate_params(_params(**overrides))


class TestNeedFallback:
    def test_short_results_need_fallback(self):
        assert RoutedRetrievalPolicy.need_fallback(3, 5)

    def test_full_results_do_not(self):
        assert not RoutedRetrievalPolicy.need_fallback(5, 5)

    def test_zero_results_need_fallback(self):
        assert RoutedRetrievalPolicy.need_fallback(0, 5)


class TestMergeFallback:
    def test_fills_up_to_top_k_and_marks_fallback(self):
        routed = [_chunk("p1")]
        hits = [_fallback_hit("h1", chunk_id="c9"), _fallback_hit("h2", chunk_id="c8")]
        merged, added = RoutedRetrievalPolicy.merge_fallback(routed, hits, top_k=3)
        assert [c.section_ref for c in merged] == ["p1", "c9", "c8"]
        assert added == 2
        assert merged[0].from_fallback is False
        assert all(c.from_fallback for c in merged[1:])

    def test_dedup_by_chunk_id_and_parent_id(self):
        """라우팅이 이미 반환한 조(parent)와 겹치는 폴백 hit 제외 (D8)."""
        routed = [_chunk("p1")]
        hits = [
            _fallback_hit("h1", chunk_id="p1"),               # parent 자체 중복
            _fallback_hit("h2", chunk_id="c1", parent_id="p1"),  # 그 조의 child
            _fallback_hit("h3", chunk_id="c2", parent_id="p9"),  # 신규
        ]
        merged, added = RoutedRetrievalPolicy.merge_fallback(routed, hits, top_k=5)
        assert [c.section_ref for c in merged] == ["p1", "c2"]
        assert added == 1

    def test_truncates_to_top_k(self):
        routed = [_chunk(f"p{i}") for i in range(5)]
        hits = [_fallback_hit("h1", chunk_id="c1")]
        merged, added = RoutedRetrievalPolicy.merge_fallback(routed, hits, top_k=5)
        assert len(merged) == 5
        assert added == 0

    def test_metadata_carried_into_chunk(self):
        hit = HybridSearchResult(
            id="h1", content="본문", score=0.02,
            bm25_rank=None, bm25_score=None, vector_rank=1, vector_score=0.9,
            source="vector_only",
            metadata={"chunk_id": "c1", "document_id": "doc-7", "clause_title": "제3조"},
        )
        merged, _ = RoutedRetrievalPolicy.merge_fallback([], [hit], top_k=5)
        chunk = merged[0]
        assert chunk.document_id == "doc-7"
        assert chunk.clause_title == "제3조"
        assert chunk.from_fallback is True
