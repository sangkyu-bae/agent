"""Multi-Query domain schemas."""
from dataclasses import dataclass, field
from typing import Optional

from typing_extensions import TypedDict

from src.domain.hybrid_search.schemas import HybridSearchResult


class MultiQueryState(TypedDict):
    """LangGraph Multi-Query Rewrite 워크플로우 State."""

    original_query: str
    request_id: str
    top_k: int
    query_type: str
    generated_queries: list[str]
    per_query_results: list[list[HybridSearchResult]]
    fused_results: list[HybridSearchResult]
    errors: list[str]
    status: str


@dataclass(frozen=True)
class QueryVariant:
    """생성된 변형 쿼리."""

    query: str
    perspective: str


@dataclass(frozen=True)
class MultiQueryResult:
    """Multi-Query 검색 최종 결과."""

    original_query: str
    query_type: str
    generated_queries: list[str]
    results: list[HybridSearchResult]
    total_found: int
    request_id: str
