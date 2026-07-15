from __future__ import annotations

from typing import TYPE_CHECKING, Set

from qdrant_client.models import FieldCondition, Filter, MatchValue

from src.application.doc_browse.chunk_assembler import (
    EXCLUDED_META_KEYS as _ASSEMBLER_EXCLUDED_META_KEYS,
    assemble_chunks_result,
    exclude_summary_payloads,
)
from src.domain.doc_browse.schemas import DocumentChunksResult

if TYPE_CHECKING:
    from qdrant_client import AsyncQdrantClient
    from src.domain.logging.interfaces.logger_interface import LoggerInterface

# 하위 호환 re-export (kb-content-browser Design §4.2 — 조립 로직은 chunk_assembler로 추출)
EXCLUDED_META_KEYS: Set[str] = _ASSEMBLER_EXCLUDED_META_KEYS

SCROLL_BATCH_LIMIT = 10_000


class GetChunksUseCase:
    def __init__(
        self,
        qdrant_client: AsyncQdrantClient,
        logger: LoggerInterface,
    ) -> None:
        self._client = qdrant_client
        self._logger = logger

    async def execute(
        self,
        collection_name: str,
        document_id: str,
        include_parent: bool = False,
    ) -> DocumentChunksResult:
        self._logger.info(
            "Get chunks started",
            collection=collection_name,
            document_id=document_id,
            include_parent=include_parent,
        )
        try:
            points = await self._scroll_filtered(collection_name, document_id)
            payloads = [self._to_payload(p) for p in points]
            # card-section-summary D9 / document-summary-routing D13:
            # 요약 계층 청크는 문서 청크 열람에서 제외
            payloads = exclude_summary_payloads(payloads)
            result = assemble_chunks_result(
                document_id, payloads, include_parent
            )
            self._logger.info(
                "Get chunks completed",
                collection=collection_name,
                document_id=document_id,
                total_chunks=result.total_chunks,
            )
            return result
        except Exception as e:
            self._logger.error(
                "Get chunks failed",
                exception=e,
                collection=collection_name,
                document_id=document_id,
            )
            raise

    @staticmethod
    def _to_payload(point) -> dict:
        payload = dict(point.payload or {})
        payload.setdefault("chunk_id", point.id)
        return payload

    async def _scroll_filtered(
        self, collection_name: str, document_id: str
    ) -> list:
        scroll_filter = Filter(
            must=[
                FieldCondition(
                    key="document_id",
                    match=MatchValue(value=document_id),
                )
            ]
        )
        points, _ = await self._client.scroll(
            collection_name=collection_name,
            scroll_filter=scroll_filter,
            limit=SCROLL_BATCH_LIMIT,
            with_vectors=False,
        )
        return list(points)
