"""WikiArticleRepository: 위키 지식 저장소 추상화 (LLM-WIKI-001).

구현은 infrastructure 레이어가 제공한다(MySQL=SoT + Qdrant/ES 색인).
request_id는 로깅/추적(LOG-001)을 위해 모든 연산에 전달한다.
"""
from abc import ABC, abstractmethod
from datetime import datetime

from src.application.wiki.schemas import WikiTreeItem
from src.domain.wiki.entity import WikiArticle, WikiStatus


class WikiArticleRepository(ABC):
    """위키 항목 영속화/조회/검색 인터페이스."""

    @abstractmethod
    async def save(self, article: WikiArticle, request_id: str) -> WikiArticle:
        """신규 위키 항목 저장(INSERT + 색인)."""

    @abstractmethod
    async def find_by_id(self, id: str, request_id: str) -> WikiArticle | None:
        """PK 단건 조회."""

    @abstractmethod
    async def find_by_agent(
        self, agent_id: str, request_id: str, status: WikiStatus | None = None
    ) -> list[WikiArticle]:
        """에이전트 스코프 목록 조회(status 필터 선택)."""

    @abstractmethod
    async def update(self, article: WikiArticle, request_id: str) -> WikiArticle:
        """기존 항목 갱신(상태 전이/편집 + 색인 갱신)."""

    @abstractmethod
    async def delete(self, id: str, request_id: str) -> bool:
        """항목 삭제. 삭제 성공 여부 반환."""

    @abstractmethod
    async def search_similar(
        self, agent_id: str, query: str, top_k: int, now: datetime, request_id: str
    ) -> list[WikiArticle]:
        """검색 노출 가능(승인+미만료) 항목을 유사도 순으로 반환.

        만료/미승인(draft, deprecated) 항목은 결과에서 제외해야 한다.
        """

    @abstractmethod
    async def list_tree_items(
        self, agent_id: str, request_id: str
    ) -> list[WikiTreeItem]:
        """지식 트리용 경량 목록(본문 제외) — path·updated_at 정렬 (wiki-user-facing)."""
