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
    ) -> tuple[list[WikiArticle], int]:
        """정제 실행 — (생성 목록, 스킵 수) 반환.

        fix-wiki-distill-dedup: 동일 refs로 이미 정제된 그룹은 LLM 호출 전에
        스킵해 재실행을 멱등하게 만든다 (FR-01/02).
        """
        self._logger.info(
            "DistillToWikiUseCase start",
            request_id=request_id,
            agent_id=agent_id,
            collection_name=collection_name,
        )
        groups = await self._source.fetch_source_groups(
            agent_id, collection_name, max_articles, request_id
        )

        # 기존 distilled 문서의 refs 키 집합 1회 구축 — 전 상태 포함(결정 ①).
        # human 문서(human:{id})는 정체성 비교에서 제외한다(결정 ②).
        existing = await self._repo.find_by_agent(agent_id, request_id)
        existing_keys = {
            WikiPolicy.refs_key(a.source_refs)
            for a in existing
            if a.source_type == WikiSourceType.DISTILLED
        }

        created: list[WikiArticle] = []
        skipped = 0
        for group in groups:
            if WikiPolicy.is_duplicate_group(group.refs, existing_keys):
                skipped += 1
                continue  # FR-02: distiller(LLM) 호출 전 스킵
            article = await self._distill_one(
                agent_id, group, collection_name, request_id
            )
            if article is not None:
                created.append(article)
                # 동일 실행 내 중복 그룹 방어
                existing_keys.add(WikiPolicy.refs_key(article.source_refs))
        self._logger.info(
            "DistillToWikiUseCase done",
            request_id=request_id,
            agent_id=agent_id,
            created_count=len(created),
            skipped_count=skipped,
        )
        return created, skipped

    async def _distill_one(
        self, agent_id: str, group: WikiSourceGroup, collection_name: str,
        request_id: str,
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
            path=collection_name,  # wiki-user-facing FR-10: 기본 분류 = 컬렉션명
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
