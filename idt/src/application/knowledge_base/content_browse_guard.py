"""KbDocumentGuard — KB 소속 문서 검증 공통 가드 (kb-content-browser Design D4).

① KnowledgeBaseUseCase.get()에 권한/존재 검증 위임
   (미존재 ValueError→404, 읽기권한 없음 PermissionError→403)
② document_metadata.kb_id 일치 검증 — 불일치/NULL이면 ValueError not found(404)
③ 통과 시 조회에 필요한 컨텍스트(collection_name 등) 반환
"""
from __future__ import annotations

from dataclasses import dataclass

from src.application.knowledge_base.use_case import KnowledgeBaseUseCase
from src.domain.auth.entities import User
from src.domain.doc_browse.interfaces import (
    DocumentMetadataRepositoryInterface,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface


@dataclass(frozen=True)
class KbDocumentContext:
    kb_id: str
    document_id: str
    collection_name: str
    filename: str
    chunk_strategy: str


class KbDocumentGuard:
    def __init__(
        self,
        kb_use_case: KnowledgeBaseUseCase,
        document_metadata_repo: DocumentMetadataRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._kb_use_case = kb_use_case
        self._repo = document_metadata_repo
        self._logger = logger

    async def ensure(
        self,
        kb_id: str,
        document_id: str,
        user: User,
        request_id: str,
    ) -> KbDocumentContext:
        await self._kb_use_case.get(kb_id, user, request_id)

        meta = await self._repo.find_by_document_id(document_id, request_id)
        if meta is None or meta.kb_id != kb_id:
            self._logger.warning(
                "KB document guard rejected",
                request_id=request_id,
                kb_id=kb_id,
                document_id=document_id,
                reason="missing" if meta is None else "kb_id mismatch",
            )
            raise ValueError(
                f"Document '{document_id}' not found in knowledge base '{kb_id}'"
            )
        return KbDocumentContext(
            kb_id=kb_id,
            document_id=document_id,
            collection_name=meta.collection_name,
            filename=meta.filename,
            chunk_strategy=meta.chunk_strategy,
        )
