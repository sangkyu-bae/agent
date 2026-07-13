"""Routed Retrieval 단계 포트 3종 (summary-routed-retrieval Design D1).

각 단계는 독립 인터페이스 — 구현 교체(문서 단계 BM25 추가, LLM 리랭커 등)가
다른 단계와 오케스트레이터에 영향을 주지 않는다 (FR-08).
"""
from abc import ABC, abstractmethod

from src.domain.routed_retrieval.schemas import (
    DocumentCandidate,
    RoutedChunk,
    RoutedParams,
    RoutedScope,
    SectionCandidate,
)


class DocumentRouterInterface(ABC):
    """1차: 질의 벡터 → 문서 후보 top-K (D3)."""

    @abstractmethod
    async def route(
        self,
        query_vector: list[float],
        scope: RoutedScope,
        top_k: int,
        request_id: str,
    ) -> list[DocumentCandidate]: ...


class SectionRouterInterface(ABC):
    """2차: 선별 문서 내 섹션 후보 top-N — 벡터+BM25 RRF (D4)."""

    @abstractmethod
    async def route(
        self,
        query: str,
        query_vector: list[float],
        document_ids: list[str],
        scope: RoutedScope,
        params: RoutedParams,
        request_id: str,
    ) -> list[SectionCandidate]: ...


class ChunkExpanderInterface(ABC):
    """3차: 섹션 후보 → 조(parent) 본문 + 근거 동봉 (D5)."""

    @abstractmethod
    async def expand(
        self,
        sections: list[SectionCandidate],
        documents_by_id: dict[str, DocumentCandidate],
        scope: RoutedScope,
        request_id: str,
    ) -> list[RoutedChunk]: ...
