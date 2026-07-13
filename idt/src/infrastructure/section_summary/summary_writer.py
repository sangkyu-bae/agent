"""DualStoreSummaryWriter — 요약 저장 (card-section-summary Design D5/D6/D7).

- 결정적 ID: uuid5("section-summary:{section_ref}") → 재시도 멱등(upsert/덮어쓰기).
- 순서: ES 먼저 → Qdrant 마지막(point 존재 = 섹션 완료 마커).
- ES 격리: content/morph_* 필드를 채우지 않아 기존 BM25에 미노출.
"""
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointStruct

from src.domain.elasticsearch.interfaces import (
    ElasticsearchRepositoryInterface,
)
from src.domain.elasticsearch.schemas import ESDocument
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.section_summary.entities import (
    SectionSummaryRecord,
    summary_id_for,
)
from src.domain.section_summary.interfaces import SummaryWriterInterface

__all__ = ["DualStoreSummaryWriter", "summary_id_for"]

_SUMMARY_CHUNK_TYPE = "section_summary"


class DualStoreSummaryWriter(SummaryWriterInterface):
    def __init__(
        self,
        qdrant_client: AsyncQdrantClient,
        es_repo: ElasticsearchRepositoryInterface,
        es_index: str,
        logger: LoggerInterface,
    ) -> None:
        self._client = qdrant_client
        self._es_repo = es_repo
        self._es_index = es_index
        self._logger = logger

    async def write(
        self, record: SectionSummaryRecord, request_id: str
    ) -> None:
        await self._es_repo.index(
            ESDocument(
                id=record.summary_id,
                body=self._es_body(record),
                index=self._es_index,
            ),
            request_id,
        )
        await self._client.upsert(
            collection_name=record.collection_name,
            points=[
                PointStruct(
                    id=record.summary_id,
                    vector=record.vector,
                    payload=self._qdrant_payload(record),
                )
            ],
        )

    @staticmethod
    def _es_body(record: SectionSummaryRecord) -> dict:
        """요약 전용 필드만 — content/morph_text/morph_keywords 없음 (D7)."""
        body = {
            "chunk_id": record.summary_id,
            "chunk_type": _SUMMARY_CHUNK_TYPE,
            "section_ref": record.section_ref,
            "clause_title": record.clause_title,
            "summary_text": record.summary_text,
            "summary_keywords": record.keywords,
            "document_id": record.document_id,
            "user_id": record.user_id,
            "collection_name": record.collection_name,
            "kb_id": record.kb_id,
        }
        if record.kb_name:
            body["kb_name"] = record.kb_name
        if record.filename:
            body["filename"] = record.filename
        return body

    @staticmethod
    def _qdrant_payload(record: SectionSummaryRecord) -> dict:
        """content=요약 텍스트, keywords는 배열 유지(MatchAny 필터 대비) (§5.1)."""
        payload = {
            "content": record.summary_text,
            "chunk_type": _SUMMARY_CHUNK_TYPE,
            "chunk_id": record.summary_id,
            "section_ref": record.section_ref,
            "document_id": record.document_id,
            "collection_name": record.collection_name,
            "kb_id": record.kb_id,
            "user_id": record.user_id,
            "clause_title": record.clause_title,
            "chunk_index": str(record.chunk_index),
            "keywords": record.keywords,
            "summary": record.summary_text,
        }
        if record.kb_name:
            payload["kb_name"] = record.kb_name
        if record.filename:
            payload["filename"] = record.filename
        return payload
