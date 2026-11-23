"""DocumentRevisionRepository — document_metadata 개정 컬럼 조회·전환.

Design Ref: document-revision §1.2 — 개정 상태의 원본(MySQL 진실). 상태 전환은 이
리포지토리만 수행하고, DocumentMetadataRepository.save 는 이 컬럼들을 건드리지 않는다.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.document_revision.interfaces import DocumentRevisionRepositoryPort
from src.domain.document_revision.value_objects import (
    DocumentVersion,
    RevisionStatus,
    SyncState,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.doc_browse.models import DocumentMetadataModel

M = DocumentMetadataModel


class DocumentRevisionRepository(DocumentRevisionRepositoryPort):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    # ── 조회 ──────────────────────────────────────────────
    async def find_version(
        self, document_id: str, request_id: str
    ) -> DocumentVersion | None:
        rows = await self._select(M.document_id == document_id)
        return rows[0] if rows else None

    async def find_lineage_versions(
        self, lineage_id: str, request_id: str
    ) -> list[DocumentVersion]:
        return await self._select(
            or_(M.lineage_id == lineage_id, M.document_id == lineage_id),
            order_by_version=True,
        )

    async def find_active_by_kb(
        self, kb_id: str, request_id: str
    ) -> list[DocumentVersion]:
        return await self._select(
            M.kb_id == kb_id, M.revision_status == RevisionStatus.ACTIVE.value
        )

    async def find_by_hash(
        self, kb_id: str, file_hash: str, request_id: str
    ) -> list[DocumentVersion]:
        return await self._select(M.kb_id == kb_id, M.file_hash == file_hash)

    async def find_pending_sync(
        self, kb_id: str, request_id: str
    ) -> list[DocumentVersion]:
        return await self._select(
            M.kb_id == kb_id, M.sync_state == SyncState.PENDING.value
        )

    # ── 전환 ──────────────────────────────────────────────
    async def assign_lineage(
        self,
        document_id: str,
        *,
        lineage_id: str | None,
        version_no: int,
        request_id: str,
    ) -> None:
        await self._update(
            document_id, request_id, "assign_lineage",
            lineage_id=lineage_id, version_no=version_no,
        )

    async def set_status(
        self,
        document_id: str,
        *,
        status: RevisionStatus,
        sync_state: SyncState,
        superseded_by: str | None,
        superseded_at: datetime | None,
        revised_by: str | None,
        request_id: str,
    ) -> None:
        await self._update(
            document_id, request_id, "set_status",
            revision_status=status.value,
            sync_state=sync_state.value,
            superseded_by=superseded_by,
            superseded_at=superseded_at,
            revised_by=revised_by,
        )

    async def set_sync_state(
        self, document_id: str, sync_state: SyncState, request_id: str
    ) -> None:
        await self._update(
            document_id, request_id, "set_sync_state", sync_state=sync_state.value
        )

    async def update_meta(
        self,
        document_id: str,
        *,
        version_label: str | None,
        effective_date: date | None,
        request_id: str,
    ) -> None:
        await self._update(
            document_id, request_id, "update_meta",
            version_label=version_label, effective_date=effective_date,
        )

    # ── 내부 ──────────────────────────────────────────────
    async def _select(self, *conditions, order_by_version: bool = False):
        stmt = select(M).where(*conditions)
        stmt = stmt.order_by(M.version_no if order_by_version else M.id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [self._to_version(r) for r in rows]

    async def _update(self, document_id, request_id, action, **values) -> None:
        self._logger.info(
            "Document revision update",
            request_id=request_id,
            document_id=document_id,
            action=action,
        )
        await self._session.execute(
            update(M).where(M.document_id == document_id).values(**values)
        )
        await self._session.flush()

    @staticmethod
    def _to_version(m: DocumentMetadataModel) -> DocumentVersion:
        return DocumentVersion(
            document_id=m.document_id,
            kb_id=m.kb_id,
            filename=m.filename,
            lineage_id=m.lineage_id,
            version_no=m.version_no or 1,
            version_label=m.version_label,
            effective_date=m.effective_date,
            revision_status=RevisionStatus(m.revision_status or "active"),
            sync_state=SyncState(m.sync_state or "synced"),
            file_hash=m.file_hash,
            superseded_by=m.superseded_by,
            superseded_at=m.superseded_at,
            revised_by=m.revised_by,
            created_at=m.created_at,
        )
