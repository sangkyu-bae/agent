"""QdrantEsChunkRevisionMarker — 청크 payload revision_status 사본 갱신.

Design Ref: document-revision §1.2 — Qdrant set_payload(filter=document_id) 1회 +
ES update_by_query(term=document_id) 1회. 둘 다 멱등이라 재시도로 맞출 수 있다.
저장소별 실패는 결과 플래그로만 알리고, 한쪽 실패가 다른 쪽 갱신을 막지 않는다.
"""
from __future__ import annotations

from typing import Any

from qdrant_client import models

from src.domain.document_revision.interfaces import ChunkRevisionMarkerPort
from src.domain.document_revision.search_guard import REVISION_STATUS_FIELD
from src.domain.document_revision.value_objects import ChunkMarkResult, RevisionStatus
from src.domain.elasticsearch.interfaces import ElasticsearchRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_SCRIPT = f"ctx._source.{REVISION_STATUS_FIELD} = params.status"


class QdrantEsChunkRevisionMarker(ChunkRevisionMarkerPort):
    def __init__(
        self,
        qdrant_client: Any,
        es_repo: ElasticsearchRepositoryInterface,
        es_index: str,
        logger: LoggerInterface,
    ) -> None:
        self._qdrant = qdrant_client
        self._es = es_repo
        self._es_index = es_index
        self._logger = logger
        self._mapping_ensured: set[str] = set()

    async def mark(
        self,
        collection_name: str,
        document_id: str,
        status: RevisionStatus,
        request_id: str,
    ) -> ChunkMarkResult:
        qdrant_ok = await self._mark_qdrant(
            collection_name, document_id, status, request_id
        )
        es_ok = await self._mark_es(document_id, status, request_id)
        self._logger.info(
            "Chunk revision mark finished",
            request_id=request_id,
            document_id=document_id,
            status=status.value,
            qdrant_ok=qdrant_ok,
            es_ok=es_ok,
        )
        return ChunkMarkResult(qdrant_ok=qdrant_ok, es_ok=es_ok)

    async def _mark_qdrant(
        self, collection_name, document_id, status, request_id
    ) -> bool:
        try:
            await self._qdrant.set_payload(
                collection_name=collection_name,
                payload={REVISION_STATUS_FIELD: status.value},
                points=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document_id),
                        )
                    ]
                ),
            )
            return True
        except Exception as e:
            self._logger.error(
                "Qdrant revision mark failed",
                exception=e,
                request_id=request_id,
                document_id=document_id,
            )
            return False

    async def _mark_es(self, document_id, status, request_id) -> bool:
        await self._ensure_mapping(request_id)
        try:
            await self._es.update_by_query(
                self._es_index,
                {"term": {"document_id": document_id}},
                {"source": _SCRIPT, "lang": "painless", "params": {"status": status.value}},
                request_id,
            )
            return True
        except Exception as e:
            self._logger.error(
                "ES revision mark failed",
                exception=e,
                request_id=request_id,
                document_id=document_id,
            )
            return False

    async def _ensure_mapping(self, request_id: str) -> None:
        """기존 인덱스에 keyword 매핑을 1회 추가. 실패해도 갱신은 진행한다.

        이미 동적 매핑(text)으로 잡혀 있으면 충돌하지만, 값이 소문자 단일 토큰이라
        term 가드는 그대로 동작한다.
        """
        if self._es_index in self._mapping_ensured:
            return
        try:
            await self._es.put_mapping(
                self._es_index, {REVISION_STATUS_FIELD: {"type": "keyword"}}, request_id
            )
        except Exception as e:
            self._logger.warning(
                "ES revision_status mapping not applied",
                exception=e,
                request_id=request_id,
                index=self._es_index,
            )
        self._mapping_ensured.add(self._es_index)
