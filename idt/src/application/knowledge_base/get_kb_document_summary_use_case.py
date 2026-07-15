"""GetKbDocumentSummaryUseCase — KB 문서 요약 본문 조회 (kb-content-browser Design §4.2).

source=qdrant|es 분기(D2), 요약 미생성 시 exists=False(D6).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from src.application.knowledge_base.browse_sources import (
    SOURCE_QDRANT,
    build_es_query,
    normalize_keywords,
    normalize_summary_text,
    scroll_qdrant_payloads,
    search_es_payloads,
    summary_metadata,
    to_int_or,
)
from src.application.knowledge_base.content_browse_guard import KbDocumentGuard
from src.domain.auth.entities import User
from src.domain.knowledge_base.browse_schemas import KbDocumentSummaryResult

if TYPE_CHECKING:
    from qdrant_client import AsyncQdrantClient
    from src.domain.elasticsearch.interfaces import (
        ElasticsearchRepositoryInterface,
    )
    from src.domain.logging.interfaces.logger_interface import LoggerInterface

_CHUNK_TYPE = "document_summary"


class GetKbDocumentSummaryUseCase:
    def __init__(
        self,
        guard: KbDocumentGuard,
        qdrant_client: "AsyncQdrantClient",
        es_repo: "ElasticsearchRepositoryInterface",
        es_index: str,
        logger: "LoggerInterface",
    ) -> None:
        self._guard = guard
        self._client = qdrant_client
        self._es_repo = es_repo
        self._es_index = es_index
        self._logger = logger

    async def execute(
        self,
        kb_id: str,
        document_id: str,
        source: str,
        user: User,
        request_id: str,
    ) -> KbDocumentSummaryResult:
        ctx = await self._guard.ensure(kb_id, document_id, user, request_id)

        payloads = await self._fetch(source, ctx, kb_id, document_id, request_id)
        self._logger.info(
            "KB document summary fetched",
            request_id=request_id,
            kb_id=kb_id,
            document_id=document_id,
            source=source,
            found=bool(payloads),
        )
        if not payloads:
            return KbDocumentSummaryResult(
                exists=False, source=source, filename=ctx.filename
            )
        return self._to_result(payloads[0], source, ctx.filename)

    async def _fetch(
        self, source, ctx, kb_id, document_id, request_id
    ) -> List[dict]:
        if source == SOURCE_QDRANT:
            return await scroll_qdrant_payloads(
                self._client,
                ctx.collection_name,
                document_id,
                chunk_type=_CHUNK_TYPE,
            )
        query = build_es_query(kb_id, document_id, chunk_type=_CHUNK_TYPE)
        return await search_es_payloads(
            self._es_repo, self._es_index, request_id, query, size=1
        )

    @staticmethod
    def _to_result(
        payload: dict, source: str, filename: str
    ) -> KbDocumentSummaryResult:
        raw_count = payload.get("section_count")
        section_count: Optional[int] = (
            to_int_or(raw_count) if raw_count is not None else None
        )
        return KbDocumentSummaryResult(
            exists=True,
            source=source,
            chunk_id=str(payload.get("chunk_id", "")),
            summary_text=normalize_summary_text(payload),
            keywords=normalize_keywords(payload),
            section_count=section_count,
            filename=str(payload.get("filename") or filename),
            metadata=summary_metadata(payload),
        )
