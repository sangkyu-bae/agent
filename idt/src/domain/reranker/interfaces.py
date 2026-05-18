"""Reranker 전략 인터페이스.

외부 의존성 없음 — abc 모듈만 사용.
"""
from abc import ABC, abstractmethod

from src.domain.reranker.schemas import RerankerRequest, RerankerResponse


class RerankerInterface(ABC):
    """Reranker 전략 인터페이스."""

    @abstractmethod
    async def rerank(self, request: RerankerRequest) -> RerankerResponse: ...
