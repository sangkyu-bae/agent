"""Reranker 도메인 스키마.

외부 의존성 없는 순수 Value Object 정의.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RerankableDocument:
    """Reranking 대상 문서."""

    id: str
    content: str
    score: float
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RerankerRequest:
    """Reranker 호출 요청."""

    query: str
    documents: list[RerankableDocument]
    top_k: int = 5
    rerank_candidates: int | None = None


@dataclass(frozen=True)
class RerankerResponse:
    """Reranker 처리 결과."""

    documents: list[RerankableDocument]
    strategy: str
    original_count: int
    reranked_count: int
