"""ListKbDocumentsUseCase — 지식베이스 문서 목록 (kb-management-ui Design §4.4).

권한/존재 검증은 KnowledgeBaseUseCase.get()에 위임(D3):
읽기권한 없음 → PermissionError(403), 미존재 → ValueError not found(404).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.application.knowledge_base.use_case import KnowledgeBaseUseCase
from src.domain.auth.entities import User
from src.domain.doc_browse.interfaces import (
    DocumentMetadataRepositoryInterface,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mysql.schemas import MySQLPaginationParams


@dataclass(frozen=True)
class KbDocumentItem:
    document_id: str
    filename: str
    chunk_count: int
    chunk_strategy: str
    created_at: datetime | None


@dataclass(frozen=True)
class KbDocumentListResult:
    kb_id: str
    kb_name: str
    documents: list[KbDocumentItem]
    total: int
    offset: int
    limit: int


class ListKbDocumentsUseCase:
    def __init__(
        self,
        kb_use_case: KnowledgeBaseUseCase,
        document_metadata_repo: DocumentMetadataRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
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
            kb_id, request_id, pagination
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
                )
                for item in page.items
            ],
            total=page.total,
            offset=offset,
            limit=limit,
        )
