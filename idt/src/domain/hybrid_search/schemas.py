"""Hybrid search domain schemas.

외부 의존성 없는 순수 Value Object 정의.
"""
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class HybridSearchRequest:
    """BM25 + 벡터 하이브리드 검색 요청."""

    query: str
    top_k: int = 10
    bm25_top_k: int = 20
    vector_top_k: int = 20
    rrf_k: int = 60
    metadata_filter: dict[str, str] = field(default_factory=dict)


@dataclass
class SearchHit:
    """BM25 또는 벡터 검색의 단일 결과 (RRF 병합 전 중간 표현)."""

    id: str
    content: str
    metadata: dict[str, str]
    raw_score: float


@dataclass(frozen=True)
class HybridSearchResult:
    """RRF 병합 후 단일 검색 결과."""

    id: str
    content: str
    score: float
    bm25_rank: Optional[int]
    bm25_score: Optional[float]
    vector_rank: Optional[int]
    vector_score: Optional[float]
    source: str           # "bm25_only" | "vector_only" | "both"
    metadata: dict[str, str]


@dataclass(frozen=True)
class HybridSearchResponse:
    """하이브리드 검색 최종 응답."""

    query: str
    results: list[HybridSearchResult]
    total_found: int
    request_id: str
