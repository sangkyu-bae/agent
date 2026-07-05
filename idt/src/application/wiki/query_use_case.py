"""WikiQueryUseCase: 위키 조회 전용 UseCase (LLM-WIKI-001).

라우터가 repository를 직접 참조하지 않도록 조회 흐름을 application 레이어로 감싼다.
"""
from src.application.repositories.wiki_repository import WikiArticleRepository
from src.domain.wiki.entity import WikiArticle, WikiStatus


class WikiQueryUseCase:
    """에이전트 스코프 위키 목록/단건 조회."""

    def __init__(self, repository: WikiArticleRepository) -> None:
        self._repo = repository

    async def list_by_agent(
        self, agent_id: str, request_id: str, status: WikiStatus | None = None
    ) -> list[WikiArticle]:
        return await self._repo.find_by_agent(agent_id, request_id, status)

    async def get_by_id(self, id: str, request_id: str) -> WikiArticle | None:
        return await self._repo.find_by_id(id, request_id)
