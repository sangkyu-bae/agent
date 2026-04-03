"""RRF (Reciprocal Rank Fusion) policy.

순수 도메인 로직: 외부 의존성 없음.
BM25 결과 + 벡터 검색 결과를 RRF 알고리즘으로 병합한다.

RRF 공식: score(d) = Σ 1 / (k + rank_i(d))
표준 k=60 (Cormack et al., 2009)
"""
from dataclasses import dataclass
from typing import Optional

from src.domain.hybrid_search.schemas import HybridSearchResult, SearchHit


@dataclass
class _RankEntry:
    """RRF 계산을 위한 내부 집계 구조."""

    id: str
    content: str
    metadata: dict[str, str]
    bm25_rank: Optional[int] = None
    bm25_score: Optional[float] = None
    vector_rank: Optional[int] = None
    vector_score: Optional[float] = None


class RRFFusionPolicy:
    """BM25와 벡터 검색 결과를 RRF로 병합하는 도메인 정책."""

    DEFAULT_K: int = 60

    def merge(
        self,
        bm25_hits: list[SearchHit],
        vector_hits: list[SearchHit],
        top_k: int,
        k: int = DEFAULT_K,
    ) -> list[HybridSearchResult]:
        """BM25 + 벡터 결과를 RRF로 병합하여 상위 top_k 반환.

        Args:
            bm25_hits: BM25 검색 결과 (rank order)
            vector_hits: 벡터 검색 결과 (rank order)
            top_k: 반환할 최대 결과 수
            k: RRF 상수 (기본값 60)

        Returns:
            RRF 점수 내림차순 정렬된 HybridSearchResult 목록
        """
        entries: dict[str, _RankEntry] = {}

        for rank, hit in enumerate(bm25_hits, start=1):
            entries[hit.id] = _RankEntry(
                id=hit.id,
                content=hit.content,
                metadata=hit.metadata,
                bm25_rank=rank,
                bm25_score=hit.raw_score,
            )

        for rank, hit in enumerate(vector_hits, start=1):
            if hit.id in entries:
                entries[hit.id].vector_rank = rank
                entries[hit.id].vector_score = hit.raw_score
            else:
                entries[hit.id] = _RankEntry(
                    id=hit.id,
                    content=hit.content,
                    metadata=hit.metadata,
                    vector_rank=rank,
                    vector_score=hit.raw_score,
                )

        results: list[HybridSearchResult] = []
        for entry in entries.values():
            rrf_score = 0.0
            if entry.bm25_rank is not None:
                rrf_score += 1.0 / (k + entry.bm25_rank)
            if entry.vector_rank is not None:
                rrf_score += 1.0 / (k + entry.vector_rank)

            if entry.bm25_rank is not None and entry.vector_rank is not None:
                source = "both"
            elif entry.bm25_rank is not None:
                source = "bm25_only"
            else:
                source = "vector_only"

            results.append(
                HybridSearchResult(
                    id=entry.id,
                    content=entry.content,
                    score=rrf_score,
                    bm25_rank=entry.bm25_rank,
                    bm25_score=entry.bm25_score,
                    vector_rank=entry.vector_rank,
                    vector_score=entry.vector_score,
                    source=source,
                    metadata=entry.metadata,
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]
