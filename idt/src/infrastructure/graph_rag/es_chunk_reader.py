"""EsChunkSource — 문서 청크를 ES 에서 읽어 추출 단위로 만든다.

Design Ref: graph-rag-foundation §2.2·§11.4 V1 — 업로드 결과는 청크 목록을 돌려주지
않으므로 document_id 로 ES 를 다시 읽는다. 단위 선택은 ExtractionUnitPolicy.
"""

from __future__ import annotations

from typing import Any

from src.domain.elasticsearch.schemas import ESSearchQuery
from src.domain.graph_rag.extraction import ChunkUnit, ExtractionUnitPolicy
from src.domain.graph_rag.interfaces import ChunkSourcePort
from src.domain.logging.interfaces.logger_interface import LoggerInterface

MAX_CHUNKS_PER_DOCUMENT = 5000
_FIELDS = [
    "chunk_id",
    "chunk_type",
    "chunk_index",
    "content",
    "document_id",
    "kb_id",
    "collection_name",
]


class EsChunkSource(ChunkSourcePort):
    def __init__(self, es_repo: Any, es_index: str, logger: LoggerInterface) -> None:
        self._es_repo = es_repo
        self._es_index = es_index
        self._logger = logger

    async def list_units(self, document_id: str, request_id: str) -> list[ChunkUnit]:
        hits = await self._es_repo.search(
            ESSearchQuery(
                index=self._es_index,
                query={"bool": {"filter": [{"term": {"document_id": document_id}}]}},
                size=MAX_CHUNKS_PER_DOCUMENT,
                source_fields=_FIELDS,
            ),
            request_id,
        )
        docs = [
            {**h.source, "chunk_id": h.source.get("chunk_id") or h.id} for h in hits
        ]
        selected = ExtractionUnitPolicy.select(docs)
        self._logger.info(
            "graph extraction units selected",
            request_id=request_id,
            document_id=document_id,
            es_chunks=len(docs),
            units=len(selected),
        )
        return [
            ChunkUnit(
                chunk_id=str(d["chunk_id"]),
                document_id=document_id,
                kb_id=d.get("kb_id"),
                collection_name=str(d.get("collection_name") or ""),
                content=str(d.get("content") or ""),
                chunk_index=int(d.get("chunk_index") or 0),
            )
            for d in selected
        ]
