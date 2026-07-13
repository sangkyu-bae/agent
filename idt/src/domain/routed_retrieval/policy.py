"""RoutedRetrievalPolicy — 파라미터 검증·폴백 판단·병합 dedup (Design D8/D13).

domain 순수 함수만 — 외부 의존 없음. 상수 1곳 집약(IterationLimitPolicy 선례).
"""
from src.domain.hybrid_search.schemas import HybridSearchResult
from src.domain.routed_retrieval.schemas import RoutedChunk, RoutedParams


class RoutedRetrievalPolicy:
    DOC_TOP_K_MIN = 1
    DOC_TOP_K_MAX = 20
    SECTION_TOP_N_MIN = 1
    SECTION_TOP_N_MAX = 50
    TOP_K_MIN = 1
    TOP_K_MAX = 30

    @classmethod
    def validate_params(cls, params: RoutedParams) -> None:
        if not (cls.DOC_TOP_K_MIN <= params.doc_top_k <= cls.DOC_TOP_K_MAX):
            raise ValueError(
                f"doc_top_k must be {cls.DOC_TOP_K_MIN}~{cls.DOC_TOP_K_MAX}"
            )
        if not (
            cls.SECTION_TOP_N_MIN
            <= params.section_top_n
            <= cls.SECTION_TOP_N_MAX
        ):
            raise ValueError(
                f"section_top_n must be "
                f"{cls.SECTION_TOP_N_MIN}~{cls.SECTION_TOP_N_MAX}"
            )
        if not (cls.TOP_K_MIN <= params.top_k <= cls.TOP_K_MAX):
            raise ValueError(f"top_k must be {cls.TOP_K_MIN}~{cls.TOP_K_MAX}")
        if params.rrf_k < 1:
            raise ValueError("rrf_k must be >= 1")
        for name, weight in (
            ("bm25_weight", params.bm25_weight),
            ("vector_weight", params.vector_weight),
        ):
            if not (0.0 <= weight <= 1.0):
                raise ValueError(f"{name} must be 0.0~1.0")

    @staticmethod
    def need_fallback(result_count: int, top_k: int) -> bool:
        """라우팅 결과가 top_k 미만이면 기존 하이브리드로 보충 (FR-05)."""
        return result_count < top_k

    @staticmethod
    def merge_fallback(
        routed: list[RoutedChunk],
        fallback_results: list[HybridSearchResult],
        top_k: int,
    ) -> tuple[list[RoutedChunk], int]:
        """폴백 보충 병합 — 조(parent) 단위 dedup + top_k 절단 (D8).

        dedup 키: 라우팅이 반환한 section_ref(=parent chunk_id) 집합.
        폴백 hit의 chunk_id 또는 parent_id가 집합에 있으면 동일 조로 간주해 제외.
        """
        seen = {chunk.section_ref for chunk in routed}
        merged = list(routed[:top_k])
        added = 0
        for hit in fallback_results:
            if len(merged) >= top_k:
                break
            chunk_id = hit.metadata.get("chunk_id", hit.id)
            parent_id = hit.metadata.get("parent_id", "")
            if chunk_id in seen or (parent_id and parent_id in seen):
                continue
            merged.append(
                RoutedChunk(
                    section_ref=chunk_id,
                    document_id=hit.metadata.get("document_id", ""),
                    content=hit.content,
                    score=hit.score,
                    clause_title=hit.metadata.get("clause_title", ""),
                    from_fallback=True,
                )
            )
            seen.add(chunk_id)
            if parent_id:
                seen.add(parent_id)
            added += 1
        return merged, added
