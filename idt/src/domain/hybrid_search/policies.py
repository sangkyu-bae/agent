"""RRF (Reciprocal Rank Fusion) policy.

순수 도메인 로직: 외부 의존성 없음.
BM25 결과 + 벡터 검색 결과를 RRF 알고리즘으로 병합한다.

RRF 공식: score(d) = Σ 1 / (k + rank_i(d))
표준 k=60 (Cormack et al., 2009)
"""
import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Optional

from src.domain.hybrid_search.schemas import HybridSearchResult, SearchHit


@dataclass(frozen=True)
class RankedList:
    """merge_many 입력 — 순위가 매겨진 결과 목록 하나와 그 가중치.

    첫 목록이 기준(primary)이다: 겹치는 청크는 기준 목록의 본문·개별 점수를 유지한다.
    """

    label: str
    hits: Sequence[HybridSearchResult]
    weight: float


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
        bm25_weight: float = 0.5,
        vector_weight: float = 0.5,
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
                rrf_score += bm25_weight * (1.0 / (k + entry.bm25_rank))
            if entry.vector_rank is not None:
                rrf_score += vector_weight * (1.0 / (k + entry.vector_rank))

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

    def merge_many(
        self,
        ranked_lists: Sequence[RankedList],
        top_k: int,
        k: int = DEFAULT_K,
    ) -> list[HybridSearchResult]:
        """이미 순위가 매겨진 결과 목록 여러 개를 가중 RRF 로 한 번 더 합친다.

        Design Ref: graph-rag-foundation §2.2 — 기존 merge 는 그대로 두고, 도구의
        최종 결과(primary)에 보조 목록(graph 등)을 합치는 용도로만 쓴다.
        source 표기: 기준 목록에만 있으면 원래 값, 보조에만 있으면 보조 label,
        둘 다면 "{원래 source}+{label}" (ai_retrieval_source.fusion_source 20자 이내).
        """
        scores: dict[str, float] = {}
        first_seen: dict[str, HybridSearchResult] = {}
        labels: dict[str, list[str]] = {}
        for position, ranked in enumerate(ranked_lists):
            seen_here: set[str] = set()
            for rank, hit in enumerate(ranked.hits, start=1):
                if hit.id in seen_here:
                    continue
                seen_here.add(hit.id)
                scores[hit.id] = scores.get(hit.id, 0.0) + ranked.weight / (k + rank)
                first_seen.setdefault(hit.id, hit)
                if position > 0:
                    labels.setdefault(hit.id, []).append(ranked.label)
        primary_ids = {h.id for h in ranked_lists[0].hits} if ranked_lists else set()
        fused = [
            dataclasses.replace(
                hit,
                score=scores[hit_id],
                source=_fused_source(
                    hit, hit_id in primary_ids, labels.get(hit_id, [])
                ),
            )
            for hit_id, hit in first_seen.items()
        ]
        fused.sort(key=lambda r: r.score, reverse=True)
        return fused[:top_k]


def _fused_source(hit: HybridSearchResult, in_primary: bool, extra: list[str]) -> str:
    if not extra:
        return hit.source
    suffix = "+".join(extra)
    return f"{hit.source}+{suffix}" if in_primary else suffix
