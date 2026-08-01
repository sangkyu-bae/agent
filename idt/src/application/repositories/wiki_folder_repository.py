"""WikiFolderSummaryRepository: 폴더 요약 저장소 추상화 (wiki-folder-summaries D1).

WikiArticleRepository와 파일을 분리해 기존 페이크에 영향을 주지 않는다(additive).
request_id는 로깅/추적(LOG-001)을 위해 모든 연산에 전달한다.
"""
from abc import ABC, abstractmethod

from src.domain.wiki.entity import WikiFolderSummary


class WikiFolderSummaryRepository(ABC):
    """폴더 요약 upsert/삭제/조회 인터페이스."""

    @abstractmethod
    async def upsert(self, summary: WikiFolderSummary, request_id: str) -> None:
        """(agent_id, path) 유니크 기준 삽입 또는 갱신 — 마지막 쓰기 승리."""

    @abstractmethod
    async def delete(self, agent_id: str, path: str, request_id: str) -> None:
        """폴더 요약 삭제(폴더 소멸 시)."""

    @abstractmethod
    async def list_by_agent(
        self, agent_id: str, request_id: str
    ) -> list[WikiFolderSummary]:
        """에이전트의 전체 폴더 요약 — path 오름차순."""
