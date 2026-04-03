"""Tests for RRF (Reciprocal Rank Fusion) policy. Domain: mock 금지."""
import pytest


def make_hit(id_, content="c", score=1.0, metadata=None):
    from src.domain.hybrid_search.schemas import SearchHit
    return SearchHit(id=id_, content=content, metadata=metadata or {}, raw_score=score)


class TestRRFFusionPolicy:
    """RRF 병합 정책 단위 테스트."""

    def test_bm25_only_result_gets_rrf_score(self):
        """BM25에만 있는 문서는 1/(k+rank) 점수를 받는다."""
        from src.domain.hybrid_search.policies import RRFFusionPolicy

        policy = RRFFusionPolicy()
        bm25 = [make_hit("doc-1", score=10.0)]
        results = policy.merge(bm25, [], top_k=10, k=60)

        assert len(results) == 1
        assert results[0].id == "doc-1"
        expected = 1.0 / (60 + 1)
        assert abs(results[0].score - expected) < 1e-9
        assert results[0].source == "bm25_only"

    def test_vector_only_result_gets_rrf_score(self):
        """벡터에만 있는 문서는 1/(k+rank) 점수를 받는다."""
        from src.domain.hybrid_search.policies import RRFFusionPolicy

        policy = RRFFusionPolicy()
        vector = [make_hit("doc-2", score=0.9)]
        results = policy.merge([], vector, top_k=10, k=60)

        assert len(results) == 1
        assert results[0].id == "doc-2"
        expected = 1.0 / (60 + 1)
        assert abs(results[0].score - expected) < 1e-9
        assert results[0].source == "vector_only"

    def test_document_in_both_gets_combined_score(self):
        """양쪽 모두에 있는 문서는 두 RRF 점수의 합을 받는다."""
        from src.domain.hybrid_search.policies import RRFFusionPolicy

        policy = RRFFusionPolicy()
        bm25 = [make_hit("shared-doc", score=8.0)]
        vector = [make_hit("shared-doc", score=0.95)]
        results = policy.merge(bm25, vector, top_k=10, k=60)

        assert len(results) == 1
        expected = 1.0 / (60 + 1) + 1.0 / (60 + 1)
        assert abs(results[0].score - expected) < 1e-9
        assert results[0].source == "both"

    def test_results_sorted_by_score_descending(self):
        """결과는 RRF 점수 내림차순으로 정렬된다."""
        from src.domain.hybrid_search.policies import RRFFusionPolicy

        policy = RRFFusionPolicy()
        # doc-A: BM25 rank 1, vector rank 1 → highest combined (두 리스트 모두 1위)
        # doc-B: BM25 rank 2, no vector → 1/(60+2)
        # doc-C: vector rank 3, no BM25 → 1/(60+3) < doc-B
        bm25 = [make_hit("doc-A"), make_hit("doc-B")]
        vector = [make_hit("doc-A"), make_hit("doc-X"), make_hit("doc-C")]
        results = policy.merge(bm25, vector, top_k=10, k=60)

        assert results[0].id == "doc-A"  # both lists → highest score
        doc_a = next(r for r in results if r.id == "doc-A")
        doc_b = next(r for r in results if r.id == "doc-B")
        doc_c = next(r for r in results if r.id == "doc-C")
        assert doc_a.score > doc_b.score > doc_c.score

    def test_top_k_limits_output(self):
        """top_k 초과 결과는 잘린다."""
        from src.domain.hybrid_search.policies import RRFFusionPolicy

        policy = RRFFusionPolicy()
        bm25 = [make_hit(f"doc-{i}") for i in range(10)]
        results = policy.merge(bm25, [], top_k=3, k=60)

        assert len(results) == 3

    def test_higher_rank_gives_lower_score(self):
        """순위가 낮을수록(숫자 클수록) RRF 점수가 낮다."""
        from src.domain.hybrid_search.policies import RRFFusionPolicy

        policy = RRFFusionPolicy()
        bm25 = [make_hit("top"), make_hit("bottom")]
        results = policy.merge(bm25, [], top_k=10, k=60)

        top_result = next(r for r in results if r.id == "top")
        bottom_result = next(r for r in results if r.id == "bottom")
        assert top_result.score > bottom_result.score

    def test_bm25_rank_and_vector_rank_recorded(self):
        """bm25_rank와 vector_rank가 결과에 기록된다."""
        from src.domain.hybrid_search.policies import RRFFusionPolicy

        policy = RRFFusionPolicy()
        bm25 = [make_hit("a"), make_hit("shared")]
        vector = [make_hit("shared"), make_hit("b")]
        results = policy.merge(bm25, vector, top_k=10, k=60)

        shared = next(r for r in results if r.id == "shared")
        assert shared.bm25_rank == 2
        assert shared.vector_rank == 1

    def test_raw_scores_preserved(self):
        """원본 점수(BM25, vector)가 결과에 보존된다."""
        from src.domain.hybrid_search.policies import RRFFusionPolicy

        policy = RRFFusionPolicy()
        bm25 = [make_hit("doc-1", score=12.5)]
        vector = [make_hit("doc-2", score=0.88)]
        results = policy.merge(bm25, vector, top_k=10, k=60)

        bm25_result = next(r for r in results if r.id == "doc-1")
        vector_result = next(r for r in results if r.id == "doc-2")
        assert bm25_result.bm25_score == 12.5
        assert vector_result.vector_score == 0.88

    def test_empty_inputs_returns_empty_list(self):
        """양쪽 모두 비어 있으면 빈 리스트를 반환한다."""
        from src.domain.hybrid_search.policies import RRFFusionPolicy

        policy = RRFFusionPolicy()
        assert policy.merge([], [], top_k=10) == []

    def test_custom_k_value_affects_score(self):
        """k 값이 달라지면 RRF 점수도 달라진다."""
        from src.domain.hybrid_search.policies import RRFFusionPolicy

        policy = RRFFusionPolicy()
        bm25 = [make_hit("d")]

        result_k60 = policy.merge(bm25, [], top_k=10, k=60)
        result_k10 = policy.merge(bm25, [], top_k=10, k=10)

        assert result_k60[0].score < result_k10[0].score  # smaller k → higher score
