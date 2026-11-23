"""SupersedeService — 구버전 전환·재활성·재반영.

Design Ref: document-revision §1.2 — 순서 고정:
  MySQL 상태 기록(sync=pending) → 청크 표식(Qdrant·ES) → 둘 다 성공 시 sync=synced.
표식이 실패하면 pending 으로 남겨 목록에서 재시도한다. 이때 청크는 아직 기존 상태라
"두 버전 모두 검색됨"(기존 동작)으로만 기울고, 근거가 비는 상태는 만들지 않는다.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from src.domain.document_revision.interfaces import (
    ChunkRevisionMarkerPort,
    DocumentRevisionRepositoryPort,
)
from src.domain.document_revision.value_objects import (
    DocumentVersion,
    RevisionStatus,
    SyncState,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class SupersedeService:
    def __init__(
        self,
        revision_repo: DocumentRevisionRepositoryPort,
        marker: ChunkRevisionMarkerPort,
        logger: LoggerInterface,
        clock: Callable[[], datetime] = datetime.utcnow,
    ) -> None:
        self._repo = revision_repo
        self._marker = marker
        self._logger = logger
        self._clock = clock

    async def supersede(
        self,
        old: DocumentVersion,
        new_document_id: str,
        collection_name: str,
        *,
        revised_by: str,
        request_id: str,
    ) -> SyncState:
        # Plan SC-1: 구버전을 검색에서 제외 (MySQL 먼저, 사본은 그 다음)
        await self._repo.set_status(
            old.document_id,
            status=RevisionStatus.SUPERSEDED,
            sync_state=SyncState.PENDING,
            superseded_by=new_document_id,
            superseded_at=self._clock(),
            revised_by=revised_by,
            request_id=request_id,
        )
        return await self._sync(
            old.document_id, collection_name, RevisionStatus.SUPERSEDED, request_id
        )

    async def reactivate(
        self, document_id: str, collection_name: str, *, request_id: str
    ) -> SyncState:
        """되돌리기·최신 삭제 시 이전 버전 복귀 (Design §4.2 #5·#9)."""
        await self._repo.set_status(
            document_id,
            status=RevisionStatus.ACTIVE,
            sync_state=SyncState.PENDING,
            superseded_by=None,
            superseded_at=None,
            revised_by=None,
            request_id=request_id,
        )
        return await self._sync(
            document_id, collection_name, RevisionStatus.ACTIVE, request_id
        )

    async def resync(
        self, version: DocumentVersion, collection_name: str, *, request_id: str
    ) -> SyncState:
        """MySQL 상태 기준으로 청크 표식만 다시 반영 (Design §4.2 #8)."""
        return await self._sync(
            version.document_id, collection_name, version.revision_status, request_id
        )

    async def _sync(
        self,
        document_id: str,
        collection_name: str,
        status: RevisionStatus,
        request_id: str,
    ) -> SyncState:
        try:
            result = await self._marker.mark(
                collection_name, document_id, status, request_id
            )
            ok = result.ok
        except Exception as e:
            self._logger.error(
                "Revision chunk mark raised",
                exception=e,
                request_id=request_id,
                document_id=document_id,
            )
            ok = False
        if not ok:
            self._logger.warning(
                "Revision sync pending",
                request_id=request_id,
                document_id=document_id,
                status=status.value,
            )
            return SyncState.PENDING
        await self._repo.set_sync_state(document_id, SyncState.SYNCED, request_id)
        return SyncState.SYNCED
