"""WikiArticleReadUseCase: 위키 단건 열람 가드 (wiki-agentic-navigation FR-02).

agent 소유 + 승인 + 미만료 항목만 반환한다. 미존재/타 에이전트/미승인/만료는
전부 None으로 수렴 — 호출 측(WikiReadTool)이 단일 실패 텍스트로 렌더링해
id 존재 여부가 LLM에 누설되지 않게 한다(오라클 차단).
"""
from datetime import datetime

from src.application.repositories.wiki_repository import WikiArticleRepository
from src.domain.wiki.entity import WikiArticle


class WikiArticleReadUseCase:
    """agent 소유 + 승인 + 미만료 위키 단건 열람."""

    def __init__(self, wiki_repo: WikiArticleRepository) -> None:
        self._wiki_repo = wiki_repo

    async def execute(
        self, article_id: str, agent_id: str, now: datetime, request_id: str
    ) -> WikiArticle | None:
        article = await self._wiki_repo.find_by_id(article_id, request_id)
        if article is None:
            return None
        if article.agent_id != agent_id:
            return None
        if not article.is_searchable(now):
            return None
        return article
