"""QdrantSectionSource — 카드 섹션 소스 v1 구현 (card-section-summary Design D1/D6).

parent(조) 청크를 document_id + chunk_type 복합 필터로 scroll하여 SectionCard로
변환한다. 후속에 장·절 단위 소스로 교체 시 이 구현만 갈아끼운다.
"""
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.section_summary.entities import (
    SectionCard,
    SectionSummaryItem,
)
from src.domain.section_summary.interfaces import SectionSourceInterface

_PARENT_CHUNK_TYPE = "parent"
_SUMMARY_CHUNK_TYPE = "section_summary"
_SCROLL_BATCH_LIMIT = 10000
_META_PASSTHROUGH_KEYS = ("user_id", "kb_id", "kb_name", "filename")


class QdrantSectionSource(SectionSourceInterface):
    def __init__(
        self, client: AsyncQdrantClient, logger: LoggerInterface
    ) -> None:
        self._client = client
        self._logger = logger

    async def list_sections(
        self, collection_name: str, document_id: str, request_id: str
    ) -> list[SectionCard]:
        points = await self._scroll(
            collection_name, document_id, _PARENT_CHUNK_TYPE
        )
        cards: list[SectionCard] = []
        for point in points:
            payload = point.payload or {}
            text = str(payload.get("content", "")).strip()
            if not text:
                self._logger.warning(
                    "Section skipped: empty content",
                    request_id=request_id,
                    document_id=document_id,
                    point_id=str(point.id),
                )
                continue
            cards.append(
                SectionCard(
                    section_ref=str(payload.get("chunk_id", point.id)),
                    title=str(payload.get("clause_title", "")),
                    text=text,
                    chunk_index=self._to_int(payload.get("chunk_index", 0)),
                    meta={
                        key: str(payload[key])
                        for key in _META_PASSTHROUGH_KEYS
                        if key in payload
                    },
                )
            )
        cards.sort(key=lambda c: c.chunk_index)
        return cards

    async def list_done_refs(
        self, collection_name: str, document_id: str, request_id: str
    ) -> set[str]:
        points = await self._scroll(
            collection_name, document_id, _SUMMARY_CHUNK_TYPE
        )
        return {
            str((point.payload or {}).get("section_ref", ""))
            for point in points
            if (point.payload or {}).get("section_ref")
        }

    async def list_summary_items(
        self, collection_name: str, document_id: str, request_id: str
    ) -> list[SectionSummaryItem]:
        """저장된 섹션 요약 전량 — 문서 요약 입력 (document-summary-routing D6)."""
        points = await self._scroll(
            collection_name, document_id, _SUMMARY_CHUNK_TYPE
        )
        items: list[SectionSummaryItem] = []
        for point in points:
            payload = point.payload or {}
            summary = str(payload.get("summary", "")).strip()
            if not summary:
                continue
            keywords = payload.get("keywords") or []
            if not isinstance(keywords, list):
                keywords = []
            items.append(
                SectionSummaryItem(
                    title=str(payload.get("clause_title", "")),
                    summary=summary,
                    keywords=[str(k) for k in keywords],
                    chunk_index=self._to_int(payload.get("chunk_index", 0)),
                    meta={
                        key: str(payload[key])
                        for key in _META_PASSTHROUGH_KEYS
                        if key in payload
                    },
                )
            )
        items.sort(key=lambda i: i.chunk_index)
        return items

    async def _scroll(
        self, collection_name: str, document_id: str, chunk_type: str
    ) -> list:
        scroll_filter = Filter(
            must=[
                FieldCondition(
                    key="document_id", match=MatchValue(value=document_id)
                ),
                FieldCondition(
                    key="chunk_type", match=MatchValue(value=chunk_type)
                ),
            ]
        )
        points, _ = await self._client.scroll(
            collection_name=collection_name,
            scroll_filter=scroll_filter,
            limit=_SCROLL_BATCH_LIMIT,
            with_vectors=False,
        )
        return list(points)

    @staticmethod
    def _to_int(value) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
