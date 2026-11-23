"""ListKbDocumentsUseCase — 지식베이스 문서 목록 (kb-management-ui Design §4.4).

권한/존재 검증은 KnowledgeBaseUseCase.get()에 위임(D3):
읽기권한 없음 → PermissionError(403), 미존재 → ValueError not found(404).
"""
from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from datetime import date, datetime

from src.application.knowledge_base.use_case import KnowledgeBaseUseCase
from src.domain.auth.entities import User
from src.domain.doc_browse.interfaces import (
    DocumentMetadataRepositoryInterface,
)
from src.domain.document_revision.interfaces import DocumentRevisionRepositoryPort
from src.domain.document_revision.value_objects import DocumentVersion
from src.domain.knowledge_base.policy import KnowledgeBasePolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mysql.schemas import MySQLPaginationParams


@dataclass(frozen=True)
class KbDocumentItem:
    document_id: str
    filename: str
    chunk_count: int
    chunk_strategy: str
    created_at: datetime | None
    # kb-document-management FR-08: 화면 버튼 노출용 서버 계산값
    can_delete: bool = False
    # document-revision §4.2 #3: 버전 표시 (목록은 active 만)
    version_no: int = 1
    version_label: str | None = None
    effective_date: date | None = None
    revision_status: str = "active"
    sync_state: str = "synced"
    lineage_id: str | None = None
    has_history: bool = False


@dataclass(frozen=True)
class KbDocumentListResult:
    kb_id: str
    kb_name: str
    documents: list[KbDocumentItem]
    total: int
    offset: int
    limit: int
    # document-revision §4.2 #3: 청크 표식 반영 실패(재시도 대상) — superseded 포함
    pending_sync: list[DocumentVersion] = field(default_factory=list)


class ListKbDocumentsUseCase:
    def __init__(
        self,
        kb_use_case: KnowledgeBaseUseCase,
        document_metadata_repo: DocumentMetadataRepositoryInterface,
        logger: LoggerInterface,
        revision_repo: DocumentRevisionRepositoryPort | None = None,
    ) -> None:
        self._revision_repo = revision_repo
        self._kb_use_case = kb_use_case
        self._repo = document_metadata_repo
        self._logger = logger

    async def execute(
        self,
        kb_id: str,
        user: User,
        request_id: str,
        offset: int = 0,
        limit: int = 20,
    ) -> KbDocumentListResult:
        kb = await self._kb_use_case.get(kb_id, user, request_id)

        pagination = MySQLPaginationParams(limit=limit, offset=offset)
        page = await self._repo.find_by_kb_id(
            kb_id, request_id, pagination, active_only=True
        )
        pending = (
            await self._revision_repo.find_pending_sync(kb_id, request_id)
            if self._revision_repo is not None
            else []
        )
        self._logger.info(
            "KB documents listed",
            request_id=request_id,
            kb_id=kb_id,
            total=page.total,
        )
        return KbDocumentListResult(
            kb_id=kb_id,
            kb_name=kb.name,
            documents=[
                KbDocumentItem(
                    document_id=item.document_id,
                    filename=item.filename,
                    chunk_count=item.chunk_count,
                    chunk_strategy=item.chunk_strategy,
                    created_at=item.created_at,
                    can_delete=KnowledgeBasePolicy.can_delete_document(
                        user, kb, item.user_id
                    ),
                    version_no=item.version_no,
                    version_label=item.version_label,
                    effective_date=item.effective_date,
                    revision_status=item.revision_status,
                    sync_state=item.sync_state,
                    lineage_id=item.lineage_id,
                    # 활성 최신본은 계보에 편입됐을 때(v2+)만 이전 버전을 가진다
                    has_history=item.lineage_id is not None,
                )
                for item in page.items
            ],
            total=page.total,
            offset=offset,
            limit=limit,
            pending_sync=pending,
        )
