"""Tests for MultiQueryPolicy and MultiQueryFusionPolicy. Domain: mock 금지."""
import pytest

from src.domain.hybrid_search.schemas import HybridSearchResult


def make_result(id_: str, score: float = 0.01, content: str = "c") -> HybridSearchResult:
    return HybridSearchResult(
        id=id_,
        content=content,
        score=score,
        bm25_rank=1,
        bm25_score=1.0,
        vector_rank=1,
        vector_score=0.9,
        source="both",
        metadata={},
    )


class TestMultiQueryPolicy:
    """MultiQueryPolicy 분류 정책 테스트."""

    def test_classify_short_query_as_ambiguous(self) -> None:
        """10자 이하 짧은 쿼리는 ambiguous로 분류."""
        from src.domain.multi_query.policy import MultiQueryPolicy

        assert MultiQueryPolicy.classify("적금 금리") == "ambiguous"

    def test_classify_very_short_query_as_ambiguous(self) -> None:
        """2~3자 초단문도 ambiguous."""
        from src.domain.multi_query.policy import MultiQueryPolicy

        assert MultiQueryPolicy.classify("금리") == "ambiguous"

    def test_classify_ambiguous_pronoun_this(self) -> None:
        """'이거' 포함 쿼리는 ambiguous."""
        from src.domain.multi_query.policy import MultiQueryPolicy

        assert MultiQueryPolicy.classify("이거 어떻게 해야 하나요") == "ambiguous"

    def test_classify_ambiguous_what(self) -> None:
        """'뭐야' 포함 쿼리는 ambiguous."""
        from src.domain.multi_query.policy import MultiQueryPolicy

        assert MultiQueryPolicy.classify("이 상품 뭐야") == "ambiguous"

    def test_classify_ambiguous_how(self) -> None:
        """'어떻게' 포함 쿼리는 ambiguous."""
        from src.domain.multi_query.policy import MultiQueryPolicy

        assert MultiQueryPolicy.classify("이 서류 어떻게 처리하나요") == "ambiguous"

    def test_classify_complex_comparison(self) -> None:
        """'비교' 포함 쿼리는 complex."""
        from src.domain.multi_query.policy import MultiQueryPolicy

        assert MultiQueryPolicy.classify("정기예금과 정기적금의 금리 비교") == "complex"

    def test_classify_complex_difference(self) -> None:
        """'차이' 포함 쿼리는 complex."""
        from src.domain.multi_query.policy import MultiQueryPolicy

        assert MultiQueryPolicy.classify("주택담보대출과 신용대출의 차이점을 알려주세요") == "complex"

    def test_classify_complex_pros_cons(self) -> None:
        """'장단점' 포함 쿼리는 complex."""
        from src.domain.multi_query.policy import MultiQueryPolicy

        assert MultiQueryPolicy.classify("변동금리 장단점에 대해 설명해주세요") == "complex"

    def test_classify_normal_query_as_simple(self) -> None:
        """충분히 긴 일반 쿼리는 simple."""
        from src.domain.multi_query.policy import MultiQueryPolicy

        assert MultiQueryPolicy.classify("2024년 한국은행 기준금리 인상 정책에 대해 알려주세요") == "simple"

    def test_classify_ambiguous_takes_priority_over_complex(self) -> None:
        """ambiguous 키워드가 complex보다 우선."""
        from src.domain.multi_query.policy import MultiQueryPolicy

        assert MultiQueryPolicy.classify("이거 비교해줘") == "ambiguous"

    def test_classify_empty_string(self) -> None:
        """빈 문자열은 ambiguous (10자 이하)."""
        from src.domain.multi_query.policy import MultiQueryPolicy

        assert MultiQueryPolicy.classify("") == "ambiguous"

    def test_calculate_per_query_top_k_five_queries(self) -> None:
        """5개 쿼리, top_k=10 → 개별 4개씩."""
        from src.domain.multi_query.policy import MultiQueryPolicy

        result = MultiQueryPolicy.calculate_per_query_top_k(10, 5)
        assert result >= 4
        assert result <= 20

    def test_calculate_per_query_top_k_single_query(self) -> None:
        """1개 쿼리면 top_k 이상."""
        from src.domain.multi_query.policy import MultiQueryPolicy

        result = MultiQueryPolicy.calculate_per_query_top_k(10, 1)
        assert result >= 10

    def test_calculate_per_query_top_k_zero_queries(self) -> None:
        """0개 쿼리면 total_top_k 그대로."""
        from src.domain.multi_query.policy import MultiQueryPolicy

        assert MultiQueryPolicy.calculate_per_query_top_k(10, 0) == 10


class TestMultiQueryFusionPolicy:
    """Cross-Query RRF 합산 정책 테스트."""

    def test_fusion_single_query_passthrough(self) -> None:
        """1개 쿼리 결과는 그대로 반환."""
        from src.domain.multi_query.policy import MultiQueryFusionPolicy

        results = [
            [make_result("doc-1", 0.5), make_result("doc-2", 0.3)],
        ]
        fused = MultiQueryFusionPolicy.fuse(results, top_k=10)

        assert len(fused) == 2
        ids = [r.id for r in fused]
        assert "doc-1" in ids
        assert "doc-2" in ids

    def test_fusion_multi_query_dedup(self) -> None:
        """여러 쿼리에서 동일 문서가 나오면 점수 누적, 중복 제거."""
        from src.domain.multi_query.policy import MultiQueryFusionPolicy

        results = [
            [make_result("shared"), make_result("only-q1")],
            [make_result("shared"), make_result("only-q2")],
            [make_result("shared"), make_result("only-q3")],
        ]
        fused = MultiQueryFusionPolicy.fuse(results, top_k=10)

        ids = [r.id for r in fused]
        assert ids.count("shared") == 1
        assert fused[0].id == "shared"

    def test_fusion_shared_doc_has_higher_score(self) -> None:
        """3개 쿼리 모두에 나온 문서가 1개 쿼리에만 나온 문서보다 높은 점수."""
        from src.domain.multi_query.policy import MultiQueryFusionPolicy

        results = [
            [make_result("shared"), make_result("unique-1")],
            [make_result("shared"), make_result("unique-2")],
            [make_result("shared"), make_result("unique-3")],
        ]
        fused = MultiQueryFusionPolicy.fuse(results, top_k=10)

        shared = next(r for r in fused if r.id == "shared")
        unique = next(r for r in fused if r.id == "unique-1")
        assert shared.score > unique.score

    def test_fusion_respects_top_k(self) -> None:
        """top_k=3이면 3개만 반환."""
        from src.domain.multi_query.policy import MultiQueryFusionPolicy

        results = [
            [make_result(f"doc-{i}") for i in range(10)],
        ]
        fused = MultiQueryFusionPolicy.fuse(results, top_k=3)

        assert len(fused) == 3

    def test_fusion_empty_results(self) -> None:
        """빈 입력은 빈 출력."""
        from src.domain.multi_query.policy import MultiQueryFusionPolicy

        assert MultiQueryFusionPolicy.fuse([], top_k=10) == []

    def test_fusion_all_empty_queries(self) -> None:
        """모든 쿼리 결과가 빈 리스트면 빈 출력."""
        from src.domain.multi_query.policy import MultiQueryFusionPolicy

        assert MultiQueryFusionPolicy.fuse([[], [], []], top_k=10) == []

    def test_fusion_custom_k_affects_score(self) -> None:
        """k 값이 다르면 점수가 다르다."""
        from src.domain.multi_query.policy import MultiQueryFusionPolicy

        results = [[make_result("doc-1")]]

        fused_k60 = MultiQueryFusionPolicy.fuse(results, top_k=10, k=60)
        fused_k10 = MultiQueryFusionPolicy.fuse(results, top_k=10, k=10)

        assert fused_k60[0].score < fused_k10[0].score

    def test_fusion_preserves_metadata(self) -> None:
        """합산 후에도 문서의 content, metadata가 보존된다."""
        from src.domain.multi_query.policy import MultiQueryFusionPolicy

        r = HybridSearchResult(
            id="doc-meta",
            content="test content",
            score=0.5,
            bm25_rank=1,
            bm25_score=5.0,
            vector_rank=2,
            vector_score=0.8,
            source="both",
            metadata={"source": "policy.pdf"},
        )
        fused = MultiQueryFusionPolicy.fuse([[r]], top_k=10)

        assert fused[0].content == "test content"
        assert fused[0].metadata == {"source": "policy.pdf"}
