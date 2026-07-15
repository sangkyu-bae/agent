"""ListKbSectionSummariesUseCase — KB 문서 섹션 요약 목록 조회 (kb-content-browser Design §4.2).

source=qdrant|es 분기(D2), chunk_index 오름차순 정렬(str→int, 실패 0).
ES body에는 chunk_index가 없어 0 기본값 (Design D5).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List

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
from src.domain.knowledge_base.browse_schemas import (
    KbSectionSummaryItem,
    KbSectionSummaryListResult,
)

if TYPE_CHECKING:
    from qdrant_client import AsyncQdrantClient
    from src.domain.elasticsearch.interfaces import (
        ElasticsearchRepositoryInterface,
    )
    from src.domain.logging.interfaces.logger_interface import LoggerInterface

_CHUNK_TYPE = "section_summary"


class ListKbSectionSummariesUseCase:
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
    ) -> KbSectionSummaryListResult:
        ctx = await self._guard.ensure(kb_id, document_id, user, request_id)

        if source == SOURCE_QDRANT:
            payloads = await scroll_qdrant_payloads(
                self._client,
                ctx.collection_name,
                document_id,
                chunk_type=_CHUNK_TYPE,
            )
        else:
            query = build_es_query(kb_id, document_id, chunk_type=_CHUNK_TYPE)
            payloads = await search_es_payloads(
                self._es_repo, self._es_index, request_id, query
            )

        items = [self._to_item(p) for p in payloads]
        items.sort(key=lambda i: i.chunk_index)
        self._logger.info(
            "KB section summaries listed",
            request_id=request_id,
            kb_id=kb_id,
            document_id=document_id,
            source=source,
            total=len(items),
        )
        return KbSectionSummaryListResult(
            source=source,
            document_id=document_id,
            total=len(items),
            items=items,
        )

    @staticmethod
    def _to_item(payload: dict) -> KbSectionSummaryItem:
        return KbSectionSummaryItem(
            chunk_id=str(payload.get("chunk_id", "")),
            section_ref=str(payload.get("section_ref", "")),
            clause_title=str(payload.get("clause_title", "")),
            chunk_index=to_int_or(payload.get("chunk_index", 0)),
            summary_text=normalize_summary_text(payload),
            keywords=normalize_keywords(payload),
            metadata=summary_metadata(payload),
        )
