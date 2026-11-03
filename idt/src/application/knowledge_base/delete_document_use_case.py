"""DeleteKbDocumentUseCase — KB 문서 단건 삭제 (kb-document-management Design §9.5).

판정 순서: 가드(KB 404·읽기 403·문서 404) → 삭제 권한 403 → 요약 잡 409 → 삭제.
메타데이터·활동 로그·잡 행은 같은 요청 세션에 묶여 함께 커밋된다.
"""
from __future__ import annotations

from datetime import datetime

from src.application.doc_browse.delete_document_use_case import (
    DeleteDocumentUseCase,
)
from src.application.knowledge_base.content_browse_guard import KbDocumentGuard
from src.domain.auth.entities import User
from src.domain.doc_browse.schemas import DeleteDocumentResult
from src.domain.knowledge_base.policy import KnowledgeBasePolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.section_summary.entities import (
    JOB_STATUS_PENDING,
    JOB_STATUS_PROCESSING,
)
from src.domain.section_summary.policy import SectionSummaryJobPolicy
from src.infrastructure.section_summary.job_repository import (
    SectionSummaryJobRepository,
)

_ACTIVE_JOB_STATUSES = (JOB_STATUS_PENDING, JOB_STATUS_PROCESSING)
_BUSY_MESSAGE = (
    "섹션 요약이 진행 중인 문서는 삭제할 수 없습니다. "
    "요약이 끝난 뒤 다시 시도해 주세요."
)


class DeleteKbDocumentUseCase:
    class DocumentBusyError(Exception):
        pass

    def __init__(
        self,
        guard: KbDocumentGuard,
        deleter: DeleteDocumentUseCase,
        job_repo: SectionSummaryJobRepository,
        policy: KnowledgeBasePolicy,
        job_policy: SectionSummaryJobPolicy,
        logger: LoggerInterface,
        stale_seconds: int,
    ) -> None:
        self._guard = guard
        self._deleter = deleter
        self._job_repo = job_repo
        self._policy = policy
        self._job_policy = job_policy
        self._logger = logger
        self._stale_seconds = stale_seconds

    async def execute(
        self, kb_id: str, document_id: str, user: User, request_id: str
    ) -> DeleteDocumentResult:
        ctx = await self._guard.ensure(kb_id, document_id, user, request_id)
        if not self._policy.can_delete_document(
            user, ctx.kb, ctx.uploader_id
        ):
            raise PermissionError(
                f"No delete access to document '{document_id}'"
            )
        await self._ensure_not_busy(document_id, request_id)
        result = await self._deleter.delete_verified(
            ctx.collection_name,
            document_id,
            ctx.filename,
            str(user.id),
            request_id,
            extra_detail={"kb_id": kb_id},
        )
        await self._job_repo.delete_by_document(document_id, request_id)
        self._logger.info(
            "KB document deleted",
            request_id=request_id,
            kb_id=kb_id,
            document_id=document_id,
        )
        return result

    async def _ensure_not_busy(
        self, document_id: str, request_id: str
    ) -> None:
        """진행 중인 잡이 삭제 후 요약을 다시 쓰는 것을 막는다 (FR-05)."""
        job = await self._job_repo.find_by_document(document_id, request_id)
        if job is None or job.status not in _ACTIVE_JOB_STATUSES:
            return
        if self._job_policy.is_stale(job, datetime.now(), self._stale_seconds):
            return
        raise self.DocumentBusyError(_BUSY_MESSAGE)
