"""DeleteKbDocumentUseCase — KB 문서 단건 삭제 (kb-document-management Design §9.5).

판정 순서: 가드(KB 404·읽기 403·문서 404) → 삭제 권한 403 → 요약 잡 409 → 삭제.
메타데이터·활동 로그·잡 행은 같은 요청 세션에 묶여 함께 커밋된다.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from src.application.doc_browse.delete_document_use_case import (
    DeleteDocumentUseCase,
)
from src.application.document_revision.supersede_service import SupersedeService
from src.application.knowledge_base.content_browse_guard import (
    KbDocumentContext,
    KbDocumentGuard,
)
from src.domain.document_revision.interfaces import DocumentRevisionRepositoryPort
from src.domain.document_revision.errors import RestorePendingError
from src.domain.document_revision.policy import RevisionPolicy
from src.domain.document_revision.value_objects import SyncState
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
        revision_repo: DocumentRevisionRepositoryPort | None = None,
        supersede_service: SupersedeService | None = None,
    ) -> None:
        # document-revision §4.2 #9: 미주입이면 이전 버전 복귀 없이 기존 동작
        self._revision_repo = revision_repo
        self._supersede = supersede_service
        self._guard = guard
        self._deleter = deleter
        self._job_repo = job_repo
        self._policy = policy
        self._job_policy = job_policy
        self._logger = logger
        self._stale_seconds = stale_seconds

    async def execute(
        self,
        kb_id: str,
        document_id: str,
        user: User,
        request_id: str,
        restore_previous: bool = False,
    ) -> DeleteDocumentResult:
        ctx = await self.check(kb_id, document_id, user, request_id)
        restored = (
            await self._restore_previous(ctx, request_id) if restore_previous else None
        )
        result = await self.delete_checked(ctx, user, request_id)
        return replace(result, restored_document_id=restored)

    async def check(
        self, kb_id: str, document_id: str, user: User, request_id: str
    ) -> KbDocumentContext:
        """삭제 가능 여부만 판정 (가드·권한·요약 잡).

        되돌리기(delete 모드)가 상태를 바꾸기 전에 먼저 호출한다.
        """
        ctx = await self._guard.ensure(kb_id, document_id, user, request_id)
        if not self._policy.can_delete_document(
            user, ctx.kb, ctx.uploader_id
        ):
            raise PermissionError(
                f"No delete access to document '{document_id}'"
            )
        await self._ensure_not_busy(document_id, request_id)
        return ctx

    async def delete_checked(
        self, ctx: KbDocumentContext, user: User, request_id: str
    ) -> DeleteDocumentResult:
        result = await self._deleter.delete_verified(
            ctx.collection_name,
            ctx.document_id,
            ctx.filename,
            str(user.id),
            request_id,
            extra_detail={"kb_id": ctx.kb_id},
        )
        await self._job_repo.delete_by_document(ctx.document_id, request_id)
        self._logger.info(
            "KB document deleted",
            request_id=request_id,
            kb_id=ctx.kb_id,
            document_id=ctx.document_id,
        )
        return result

    async def _restore_previous(
        self, ctx: KbDocumentContext, request_id: str
    ) -> str | None:
        """활성 최신 버전을 지우면 이전 버전을 먼저 검색에 복귀시킨다 (근거 공백 방지)."""
        if self._revision_repo is None or self._supersede is None:
            return None
        current = await self._revision_repo.find_version(ctx.document_id, request_id)
        if current is None or not current.is_active or current.version_no <= 1:
            return None
        lineage = await self._revision_repo.find_lineage_versions(
            current.effective_lineage_id, request_id
        )
        previous = RevisionPolicy.previous_version(current, lineage)
        if previous is None:
            return None
        sync = await self._supersede.reactivate(
            previous.document_id, ctx.collection_name, request_id=request_id
        )
        if sync is not SyncState.SYNCED:
            # Act-1 I2: 이전 버전이 검색에 돌아오지 못했으면 삭제를 멈춘다.
            # 요청 실패로 MySQL 은 롤백되므로 청크 표식도 superseded 로 되돌린다(최선 시도).
            try:
                await self._supersede.resync(
                    previous, ctx.collection_name, request_id=request_id
                )
            except Exception as e:
                self._logger.error(
                    "Restore revert failed", request_id=request_id,
                    document_id=previous.document_id, exception=e,
                )
            raise RestorePendingError(
                "restore_pending",
                "이전 버전을 검색에 다시 넣지 못해 삭제를 멈췄습니다. "
                "잠시 후 다시 시도해 주세요.",
            )
        return previous.document_id

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
