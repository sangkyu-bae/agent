"""HumanWikiWriteUseCase: 소유자 직접 작성/편집/폐기 (wiki-user-facing).

거버넌스는 "전파 범위" 기준:
- agent 스코프(자기 에이전트)의 human 문서는 셀프서비스 — 생성 즉시 approved.
- 인가는 WikiPolicy.can_manage(admin 전부 / 소유자는 human만).
- 검색 노출 조건(is_searchable)은 불변 — human 문서도 동일 게이트를 지난다.

인가 실패는 PermissionError(→403), 미존재/불변식 위반은 ValueError(→404/422).
wiki·agent 두 repository는 동일 세션으로 주입한다(한 UseCase 한 세션).
"""
import dataclasses
import uuid
from datetime import datetime

from src.application.repositories.wiki_repository import WikiArticleRepository
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.wiki.entity import WikiArticle, WikiSourceType, WikiStatus
from src.domain.wiki.policies import WikiPolicy


class HumanWikiWriteUseCase:
    """사람 작성 위키 문서의 생성/편집/폐기."""

    def __init__(
        self,
        wiki_repo: WikiArticleRepository,
        agent_repo: AgentDefinitionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._wiki_repo = wiki_repo
        self._agent_repo = agent_repo
        self._logger = logger

    async def create(
        self,
        agent_id: str,
        title: str,
        content: str,
        path: str | None,
        actor_id: str,
        actor_is_admin: bool,
        request_id: str,
        valid_until: datetime | None = None,
    ) -> WikiArticle:
        """human 문서를 생성한다 — agent 스코프 셀프서비스, 즉시 approved."""
        owner_id = await self._get_owner_id(agent_id, request_id)
        if not actor_is_admin and actor_id != owner_id:
            raise PermissionError("본인 소유 에이전트에만 문서를 작성할 수 있습니다.")
        WikiPolicy.validate_path(path)
        now = datetime.utcnow()
        article = WikiArticle(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            title=title,
            content=content,
            source_type=WikiSourceType.HUMAN,
            source_refs=[WikiPolicy.human_source_ref(actor_id)],
            status=WikiStatus.APPROVED,
            valid_until=valid_until,
            editor_id=actor_id,
            reviewer_id=actor_id,
            created_at=now,
            updated_at=now,
            path=path,
        )
        WikiPolicy.validate_for_creation(article)
        self._logger.info(
            "HumanWikiWriteUseCase create",
            request_id=request_id, agent_id=agent_id, actor_id=actor_id,
        )
        return await self._wiki_repo.save(article, request_id)

    async def edit(
        self,
        article_id: str,
        title: str,
        content: str,
        path: str | None,
        actor_id: str,
        actor_is_admin: bool,
        request_id: str,
    ) -> WikiArticle:
        """문서를 편집한다(version++). 소유자는 human 문서만."""
        article = await self._get_managed(
            article_id, actor_id, actor_is_admin, request_id
        )
        WikiPolicy.validate_path(path)
        candidate = dataclasses.replace(article, title=title, content=content)
        WikiPolicy.validate_for_creation(candidate)  # 제목/본문 불변식 재사용
        article.apply_edit(title, content, datetime.utcnow())
        article.editor_id = actor_id
        article.path = path
        self._logger.info(
            "HumanWikiWriteUseCase edit",
            request_id=request_id, id=article_id, version=article.version,
        )
        return await self._wiki_repo.update(article, request_id)

    async def deprecate(
        self,
        article_id: str,
        actor_id: str,
        actor_is_admin: bool,
        request_id: str,
    ) -> WikiArticle:
        """문서를 폐기한다(검색 즉시 제외). 소유자는 human 문서만."""
        article = await self._get_managed(
            article_id, actor_id, actor_is_admin, request_id
        )
        WikiPolicy.validate_transition(article.status, WikiStatus.DEPRECATED)
        article.mark_deprecated(datetime.utcnow())
        self._logger.info(
            "HumanWikiWriteUseCase deprecate", request_id=request_id, id=article_id,
        )
        return await self._wiki_repo.update(article, request_id)

    async def _get_managed(
        self, article_id: str, actor_id: str, actor_is_admin: bool, request_id: str
    ) -> WikiArticle:
        """항목 조회 + can_manage 인가. 미존재 ValueError, 인가 실패 PermissionError."""
        article = await self._wiki_repo.find_by_id(article_id, request_id)
        if article is None:
            raise ValueError(f"위키 항목을 찾을 수 없습니다: {article_id}")
        owner_id = await self._get_owner_id(article.agent_id, request_id)
        if not WikiPolicy.can_manage(article, actor_id, actor_is_admin, owner_id):
            raise PermissionError("이 문서를 관리할 권한이 없습니다.")
        return article

    async def _get_owner_id(self, agent_id: str, request_id: str) -> str:
        agent = await self._agent_repo.find_by_id(agent_id, request_id)
        if agent is None:
            raise ValueError(f"에이전트를 찾을 수 없습니다: {agent_id}")
        return agent.user_id
