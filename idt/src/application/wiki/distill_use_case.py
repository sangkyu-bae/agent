"""DistillToWikiUseCase: 원본 문서 → 정제 위키 draft 생성 (LLM-WIKI-001, Phase 1/B).

동작 흐름:
1. source_provider로 에이전트 컬렉션의 원본 청크 그룹 조회
2. 각 그룹을 distiller(LLM)로 요약 → 제목/본문
3. WikiArticle(status=draft) 구성 후 WikiPolicy로 불변식 검증
4. 검증 통과분만 repo에 저장(출처 불변식 위반 그룹은 건너뜀)

자동 생성분은 항상 draft로 시작한다(승인 전 검색 비노출 — 보수적 기본값).
"""
import uuid
from datetime import datetime

from src.application.repositories.wiki_repository import WikiArticleRepository
from src.application.wiki.interfaces import WikiDistillerInterface, WikiSourceProvider
from src.application.wiki.schemas import WikiSourceGroup
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.wiki.entity import WikiArticle, WikiSourceType, WikiStatus
from src.domain.wiki.policies import WikiPolicy


class DistillToWikiUseCase:
    """원본 청크를 정제해 draft 위키 항목으로 적재한다."""

    def __init__(
        self,
        repository: WikiArticleRepository,
        source_provider: WikiSourceProvider,
        distiller: WikiDistillerInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repo = repository
        self._source = source_provider
        self._distiller = distiller
        self._logger = logger

    async def execute(
        self, agent_id: str, collection_name: str, max_articles: int, request_id: str
    ) -> list[WikiArticle]:
        self._logger.info(
            "DistillToWikiUseCase start",
            request_id=request_id,
            agent_id=agent_id,
            collection_name=collection_name,
        )
        groups = await self._source.fetch_source_groups(
            agent_id, collection_name, max_articles, request_id
        )
        created: list[WikiArticle] = []
        for group in groups:
            article = await self._distill_one(agent_id, group, request_id)
            if article is not None:
                created.append(article)
        self._logger.info(
            "DistillToWikiUseCase done",
            request_id=request_id,
            agent_id=agent_id,
            created_count=len(created),
        )
        return created

    async def _distill_one(
        self, agent_id: str, group: WikiSourceGroup, request_id: str
    ) -> WikiArticle | None:
        """단일 그룹을 정제·검증·저장한다. 불변식 위반 시 None(건너뜀)."""
        distilled = await self._distiller.distill(group, request_id)
        now = datetime.utcnow()
        article = WikiArticle(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            title=distilled.title,
            content=distilled.content,
            source_type=WikiSourceType.DISTILLED,
            source_refs=group.refs,
            status=WikiStatus.DRAFT,
            created_at=now,
            updated_at=now,
        )
        try:
            WikiPolicy.validate_for_creation(article)
        except ValueError as exc:
            self._logger.warning(
                "DistillToWikiUseCase skip group (invariant)",
                request_id=request_id,
                reason=str(exc),
            )
            return None
        return await self._repo.save(article, request_id)
