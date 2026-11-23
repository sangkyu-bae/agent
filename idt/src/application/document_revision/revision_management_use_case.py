"""RevisionManagementUseCase — 버전 이력·되돌리기·사후 연결·메타·재반영.

Design Ref: document-revision §4.2 #4~#8.
- 읽기(이력)는 KB 읽기 권한, 나머지는 KB 쓰기 권한.
- 되돌리기는 이전 버전을 먼저 다시 활성화한 뒤 현재 버전을 분리/삭제한다.
  delete 모드는 삭제 가능 여부(권한·요약 잡)를 상태 변경 전에 먼저 판정한다.
- 수동 연결·되돌리기는 판정 로그에 남긴다 (auto 임계값 실측 자료).
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from src.application.document_revision.supersede_service import SupersedeService
from src.application.knowledge_base.content_browse_guard import (
    KbDocumentContext,
    KbDocumentGuard,
)
from src.domain.auth.entities import User
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.document_revision.errors import RevisionLinkInvalidError
from src.domain.document_revision.filename_normalizer import normalize_filename
from src.domain.document_revision.interfaces import (
    DocumentRevisionRepositoryPort,
    RevisionCheckLogRepositoryPort,
)
from src.domain.document_revision.policy import RevisionPolicy
from src.domain.document_revision.value_objects import (
    CheckDecision,
    CheckSource,
    DocumentVersion,
    LlmStatus,
    RevisionCheckLogEntry,
    RollbackMode,
    SyncState,
)
from src.domain.knowledge_base.policy import KnowledgeBasePolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface


@dataclass(frozen=True)
class RollbackResult:
    restored_document_id: str
    detached_document_id: str | None
    deleted_document_id: str | None
    sync_state: str


class RevisionManagementUseCase:
    def __init__(
        self,
        guard: KbDocumentGuard,
        policy: KnowledgeBasePolicy,
        dept_repo: DepartmentRepositoryInterface,
        revision_repo: DocumentRevisionRepositoryPort,
        supersede_service: SupersedeService,
        kb_deleter,  # DeleteKbDocumentUseCase (check / delete_checked)
        check_log_repo: RevisionCheckLogRepositoryPort,
        logger: LoggerInterface,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self._guard = guard
        self._policy = policy
        self._dept_repo = dept_repo
        self._repo = revision_repo
        self._supersede = supersede_service
        self._deleter = kb_deleter
        self._log = check_log_repo
        self._logger = logger
        self._new_id = id_factory

    # ── 조회 ──────────────────────────────────────────────
    async def versions(
        self, kb_id: str, document_id: str, user: User, request_id: str
    ) -> list[DocumentVersion]:
        await self._guard.ensure(kb_id, document_id, user, request_id)
        current = await self._require(document_id, request_id)
        lineage = await self._repo.find_lineage_versions(
            current.effective_lineage_id, request_id
        )
        return sorted(lineage, key=lambda v: v.version_no, reverse=True)

    # ── 되돌리기 ──────────────────────────────────────────
    async def rollback(
        self,
        kb_id: str,
        document_id: str,
        mode: RollbackMode,
        user: User,
        request_id: str,
    ) -> RollbackResult:
        ctx = await self._writable(kb_id, document_id, user, request_id)
        current = await self._require(document_id, request_id)
        lineage = await self._repo.find_lineage_versions(
            current.effective_lineage_id, request_id
        )
        previous = RevisionPolicy.validate_rollback(current, lineage)
        delete_ctx = None
        if mode is RollbackMode.DELETE:
            delete_ctx = await self._deleter.check(kb_id, document_id, user, request_id)

        sync = await self._supersede.reactivate(
            previous.document_id, ctx.collection_name, request_id=request_id
        )
        if mode is RollbackMode.DELETE and sync is not SyncState.SYNCED:
            # Act-1 I2: 이전 버전 청크가 아직 검색 제외 상태면 지우지 않는다(근거 공백 방지).
            self._logger.warning(
                "Rollback delete downgraded to detach (restore pending)",
                request_id=request_id, document_id=document_id,
            )
            mode = RollbackMode.DETACH
        if mode is RollbackMode.DETACH:
            await self._repo.assign_lineage(
                document_id, lineage_id=None, version_no=1, request_id=request_id
            )
            # Act-1 M5: 독립 문서에 이전 계보의 라벨·시행일을 남기지 않는다
            await self._repo.update_meta(
                document_id, version_label=None, effective_date=None,
                request_id=request_id,
            )
        else:
            await self._deleter.delete_checked(delete_ctx, user, request_id)

        decision = (
            CheckDecision.ROLLBACK_DETACH
            if mode is RollbackMode.DETACH
            else CheckDecision.ROLLBACK_DELETE
        )
        await self._write_log(
            kb_id, user, current, CheckSource.ROLLBACK, decision,
            target=previous.document_id, request_id=request_id,
        )
        self._logger.info(
            "Revision rolled back",
            request_id=request_id, kb_id=kb_id, document_id=document_id,
            restored_document_id=previous.document_id, mode=mode.value,
        )
        return RollbackResult(
            restored_document_id=previous.document_id,
            detached_document_id=document_id if mode is RollbackMode.DETACH else None,
            deleted_document_id=document_id if mode is RollbackMode.DELETE else None,
            sync_state=sync.value,
        )

    # ── 사후 연결 ─────────────────────────────────────────
    async def link(
        self,
        kb_id: str,
        document_id: str,
        supersedes_document_id: str,
        user: User,
        request_id: str,
    ) -> tuple[DocumentVersion, SyncState]:
        ctx = await self._writable(kb_id, document_id, user, request_id)
        source = await self._repo.find_version(document_id, request_id)
        target = await self._repo.find_version(supersedes_document_id, request_id)
        if source is None or target is None:
            raise RevisionLinkInvalidError("not_found")
        source_lineage = await self._repo.find_lineage_versions(
            source.effective_lineage_id, request_id
        )
        target_lineage = await self._repo.find_lineage_versions(
            target.effective_lineage_id, request_id
        )
        RevisionPolicy.validate_link(
            source, target, kb_id, source_lineage, target_lineage
        )
        await self._repo.assign_lineage(
            document_id,
            lineage_id=target.effective_lineage_id,
            version_no=RevisionPolicy.next_version_no(target_lineage),
            request_id=request_id,
        )
        sync = await self._supersede.supersede(
            target, document_id, ctx.collection_name,
            revised_by=str(user.id), request_id=request_id,
        )
        await self._write_log(
            kb_id, user, source, CheckSource.MANUAL_LINK, CheckDecision.REVISION,
            target=target.document_id, request_id=request_id,
        )
        return await self._require(document_id, request_id), sync

    # ── 메타 · 재반영 ─────────────────────────────────────
    async def update_meta(
        self,
        kb_id: str,
        document_id: str,
        version_label: str | None,
        effective_date: date | None,
        user: User,
        request_id: str,
    ) -> DocumentVersion:
        await self._writable(kb_id, document_id, user, request_id)
        await self._require(document_id, request_id)
        await self._repo.update_meta(
            document_id, version_label=version_label,
            effective_date=effective_date, request_id=request_id,
        )
        return await self._require(document_id, request_id)

    async def resync(
        self, kb_id: str, document_id: str, user: User, request_id: str
    ) -> DocumentVersion:
        ctx = await self._writable(kb_id, document_id, user, request_id)
        version = await self._require(document_id, request_id)
        await self._supersede.resync(version, ctx.collection_name, request_id=request_id)
        return await self._require(document_id, request_id)

    # ── 내부 ──────────────────────────────────────────────
    async def _writable(
        self, kb_id: str, document_id: str, user: User, request_id: str
    ) -> KbDocumentContext:
        ctx = await self._guard.ensure(kb_id, document_id, user, request_id)
        dept_ids: list[str] = []
        if user.id is not None:
            depts = await self._dept_repo.find_departments_by_user(user.id, request_id)
            dept_ids = [d.department_id for d in depts]
        if not self._policy.can_write(user, ctx.kb, dept_ids):
            raise PermissionError(f"No write access to knowledge base '{kb_id}'")
        return ctx

    async def _require(self, document_id: str, request_id: str) -> DocumentVersion:
        version = await self._repo.find_version(document_id, request_id)
        if version is None:
            raise ValueError(f"Document '{document_id}' not found")
        return version

    async def _write_log(
        self,
        kb_id: str,
        user: User,
        doc: DocumentVersion,
        source: CheckSource,
        decision: CheckDecision,
        *,
        target: str | None,
        request_id: str,
    ) -> None:
        try:
            await self._log.save(
                RevisionCheckLogEntry(
                    check_id=self._new_id(), kb_id=kb_id, user_id=str(user.id),
                    source=source, filename=doc.filename,
                    normalized_name=normalize_filename(doc.filename),
                    file_hash=doc.file_hash, verdict="manual",
                    suggested_document_id=None, candidates=[],
                    llm_status=LlmStatus.SKIPPED, elapsed_ms=0, parse_ms=0,
                    decision=decision, target_document_id=target,
                    decided_document_id=doc.document_id, decided_by=str(user.id),
                ),
                request_id,
            )
        except Exception as e:
            self._logger.warning(
                "Revision manual log failed", request_id=request_id, exception=e
            )
