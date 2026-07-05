"""Application 인터페이스: 위키 정제용 외부 의존 추상화 (LLM-WIKI-001).

구현은 infrastructure 레이어가 제공한다(원본 청크 조회=RAG, 요약=LLM).
"""
from abc import ABC, abstractmethod

from src.application.wiki.schemas import DistilledContent, WikiSourceGroup


class WikiSourceProvider(ABC):
    """정제 대상 원본 청크를 주제/섹션 단위로 묶어 제공한다."""

    @abstractmethod
    async def fetch_source_groups(
        self, agent_id: str, collection_name: str, max_articles: int, request_id: str
    ) -> list[WikiSourceGroup]:
        """에이전트 컬렉션의 원본 청크를 그룹으로 반환."""


class WikiDistillerInterface(ABC):
    """원본 청크 그룹을 LLM으로 요약해 위키 본문을 생성한다."""

    @abstractmethod
    async def distill(
        self, group: WikiSourceGroup, request_id: str
    ) -> DistilledContent:
        """청크 그룹 → 정제된 제목/본문."""
