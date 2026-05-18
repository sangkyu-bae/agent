"""Multi-Query domain policies."""
from src.domain.hybrid_search.schemas import HybridSearchResult


class MultiQueryPolicy:
    """Multi-Query 생성 관련 도메인 정책."""

    MAX_GENERATED_QUERIES: int = 5
    MIN_GENERATED_QUERIES: int = 3
    SHORT_QUERY_THRESHOLD: int = 10

    AMBIGUOUS_INDICATORS: list[str] = [
        "이거", "그거", "저거", "그것", "이것", "저것",
        "뭐야", "뭐", "어떻게", "왜",
    ]

    COMPLEX_INDICATORS: list[str] = [
        "비교", "차이", "장단점", "vs", "어떤 것",
        "~와 ~의", "관계", "영향",
    ]

    @classmethod
    def classify(cls, query: str) -> str:
        """쿼리를 simple / complex / ambiguous로 분류."""
        stripped = query.strip()

        for indicator in cls.AMBIGUOUS_INDICATORS:
            if indicator in stripped:
                return "ambiguous"

        for indicator in cls.COMPLEX_INDICATORS:
            if indicator in stripped:
                return "complex"

        if len(stripped) <= cls.SHORT_QUERY_THRESHOLD:
            return "ambiguous"

        return "simple"

    @classmethod
    def calculate_per_query_top_k(
        cls, total_top_k: int, query_count: int
    ) -> int:
        """쿼리 수에 따라 개별 검색 top_k 조정."""
        if query_count <= 0:
            return total_top_k
        per_k = max(total_top_k, total_top_k * 2 // query_count)
        return min(per_k, total_top_k * 2)


class MultiQueryFusionPolicy:
    """Cross-Query RRF 합산 정책."""

    DEFAULT_K: int = 60

    @classmethod
    def fuse(
        cls,
        per_query_results: list[list[HybridSearchResult]],
        top_k: int,
        k: int = DEFAULT_K,
    ) -> list[HybridSearchResult]:
        """N개 쿼리 검색 결과를 RRF로 합산."""
        scores: dict[str, float] = {}
        doc_map: dict[str, HybridSearchResult] = {}

        for query_results in per_query_results:
            for rank, result in enumerate(query_results, start=1):
                rrf_score = 1.0 / (k + rank)
                scores[result.id] = scores.get(result.id, 0.0) + rrf_score
                if result.id not in doc_map or result.score > doc_map[result.id].score:
                    doc_map[result.id] = result

        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

        fused: list[HybridSearchResult] = []
        for doc_id in sorted_ids[:top_k]:
            original = doc_map[doc_id]
            fused.append(
                HybridSearchResult(
                    id=original.id,
                    content=original.content,
                    score=scores[doc_id],
                    bm25_rank=original.bm25_rank,
                    bm25_score=original.bm25_score,
                    vector_rank=original.vector_rank,
                    vector_score=original.vector_score,
                    source=original.source,
                    metadata=original.metadata,
                )
            )
        return fused
