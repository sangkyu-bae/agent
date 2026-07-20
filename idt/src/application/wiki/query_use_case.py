"""WikiQueryUseCase: 위키 조회 전용 UseCase (LLM-WIKI-001).

라우터가 repository를 직접 참조하지 않도록 조회 흐름을 application 레이어로 감싼다.
"""
from dataclasses import dataclass

from src.application.repositories.wiki_repository import WikiArticleRepository
from src.application.wiki.schemas import WikiTreeItem
from src.domain.wiki.entity import WikiArticle, WikiStatus


@dataclass
class WikiTreeGroup:
    """path 문자열 단위 그룹 — 계층(트리) 조립은 프론트 담당 (wiki-user-facing)."""

    path: str | None  # None = 미분류
    items: list[WikiTreeItem]


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

    async def list_tree(
        self, agent_id: str, request_id: str
    ) -> list[WikiTreeGroup]:
        """path 단위 그룹 목록 — 그룹 순서는 저장소 정렬(미분류 마지막) 첫 등장 순."""
        items = await self._repo.list_tree_items(agent_id, request_id)
        groups: dict[str | None, WikiTreeGroup] = {}
        for item in items:
            group = groups.get(item.path)
            if group is None:
                group = WikiTreeGroup(path=item.path, items=[])
                groups[item.path] = group
            group.items.append(item)
        return list(groups.values())
