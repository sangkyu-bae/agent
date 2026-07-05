"""WikiReviewUseCase: 위키 거버넌스(승인/반려/폐기/복구/편집) (LLM-WIKI-001, Phase 2/C).

모든 상태 전이는 WikiPolicy.validate_transition으로 검증한 뒤 수행한다.
미존재 항목/허용되지 않은 전이/검증 실패는 ValueError로 차단한다.
"""
import dataclasses
from datetime import datetime

from src.application.repositories.wiki_repository import WikiArticleRepository
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.wiki.entity import WikiArticle, WikiStatus
from src.domain.wiki.policies import WikiPolicy


class WikiReviewUseCase:
    """위키 항목 라이프사이클 관리(거버넌스 게이트)."""

    def __init__(
        self, repository: WikiArticleRepository, logger: LoggerInterface
    ) -> None:
        self._repo = repository
        self._logger = logger

    async def approve(
        self, article_id: str, reviewer_id: str, request_id: str
    ) -> WikiArticle:
        """초안을 승인 상태로 전이한다(draft→approved)."""
        return await self._to_approved(
            article_id, reviewer_id, request_id, expected_from=WikiStatus.DRAFT
        )

    async def restore(
        self, article_id: str, reviewer_id: str, request_id: str
    ) -> WikiArticle:
        """폐기 항목을 승인 상태로 복구한다(deprecated→approved)."""
        return await self._to_approved(
            article_id, reviewer_id, request_id, expected_from=WikiStatus.DEPRECATED
        )

    async def reject(self, article_id: str, request_id: str) -> WikiArticle:
        """초안을 반려(폐기) 상태로 전이한다(draft→deprecated)."""
        return await self._to_deprecated(article_id, request_id)

    async def deprecate(self, article_id: str, request_id: str) -> WikiArticle:
        """승인 항목을 폐기 상태로 전이한다(approved→deprecated)."""
        return await self._to_deprecated(article_id, request_id)

    async def edit(
        self,
        article_id: str,
        title: str,
        content: str,
        editor_id: str,
        request_id: str,
    ) -> WikiArticle:
        """본문/제목을 수정하고 버전을 올린다(사람 편집)."""
        article = await self._get(article_id, request_id)
        candidate = dataclasses.replace(article, title=title, content=content)
        WikiPolicy.validate_for_creation(candidate)  # 제목/본문 검증 재사용
        article.apply_edit(title, content, datetime.utcnow())
        article.editor_id = editor_id
        self._logger.info(
            "WikiReviewUseCase edit", request_id=request_id, id=article_id,
            version=article.version,
        )
        return await self._repo.update(article, request_id)

    async def _to_approved(
        self,
        article_id: str,
        reviewer_id: str,
        request_id: str,
        expected_from: WikiStatus,
    ) -> WikiArticle:
        article = await self._get(article_id, request_id)
        if article.status != expected_from:
            raise ValueError(
                f"허용되지 않은 상태 전이입니다: {article.status.value} -> approved"
            )
        WikiPolicy.validate_transition(article.status, WikiStatus.APPROVED)
        article.mark_approved(reviewer_id, datetime.utcnow())
        self._logger.info(
            "WikiReviewUseCase approved", request_id=request_id, id=article_id
        )
        return await self._repo.update(article, request_id)

    async def _to_deprecated(self, article_id: str, request_id: str) -> WikiArticle:
        article = await self._get(article_id, request_id)
        WikiPolicy.validate_transition(article.status, WikiStatus.DEPRECATED)
        article.mark_deprecated(datetime.utcnow())
        self._logger.info(
            "WikiReviewUseCase deprecated", request_id=request_id, id=article_id
        )
        return await self._repo.update(article, request_id)

    async def _get(self, article_id: str, request_id: str) -> WikiArticle:
        article = await self._repo.find_by_id(article_id, request_id)
        if article is None:
            raise ValueError(f"위키 항목을 찾을 수 없습니다: {article_id}")
        return article
