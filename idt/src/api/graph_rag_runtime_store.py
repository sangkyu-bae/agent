"""RuntimeGraphStore — 실행 시점의 store 로 위임하는 GraphStorePort.

Design Ref: graph-rag-foundation §11.6 M2-5 — 기동 시 차원 불일치면 store 를 끄는데,
조립 시점에 만든 러너·검색 소스가 꺼지기 전 store 를 붙잡지 않게 매 호출마다
현재 store 를 찾는다. 없으면 GraphBackendUnavailableError.
"""

from __future__ import annotations

from collections.abc import Callable

from src.domain.graph_rag.exceptions import GraphBackendUnavailableError
from src.domain.graph_rag.extraction import ChunkGraphWrite, EntityWrite
from src.domain.graph_rag.interfaces import GraphStorePort
from src.domain.graph_rag.resolution import Candidate


class RuntimeGraphStore(GraphStorePort):
    def __init__(self, current: Callable[[], GraphStorePort | None]) -> None:
        self._current = current

    def _store(self) -> GraphStorePort:
        store = self._current()
        if store is None:
            raise GraphBackendUnavailableError("graph backend not available")
        return store

    def available(self) -> bool:
        return self._current() is not None

    async def ping(self) -> None:
        await self._store().ping()

    async def counts(self) -> tuple[int, int]:
        return await self._store().counts()

    async def ensure_schema(self, embedding_dimensions: int) -> None:
        await self._store().ensure_schema(embedding_dimensions)

    async def aclose(self) -> None:  # 수명은 graph_rag_di 가 관리
        return None

    async def extracted_chunk_ids(self, document_id: str, version: str) -> set[str]:
        return await self._store().extracted_chunk_ids(document_id, version)

    async def delete_document(self, document_id: str) -> None:
        await self._store().delete_document(document_id)

    async def find_entity_id(
        self, scope_key: str, normalized_name: str, type_: str
    ) -> str | None:
        return await self._store().find_entity_id(scope_key, normalized_name, type_)

    async def write_chunk_graph(self, write: ChunkGraphWrite) -> None:
        await self._store().write_chunk_graph(write)

    async def find_candidates(
        self,
        scope_key: str,
        normalized_name: str,
        embedding: list[float] | None,
        limit: int,
    ) -> list[Candidate]:
        return await self._store().find_candidates(
            scope_key, normalized_name, embedding, limit
        )

    async def reassign_decision(self, decision_id: str, to_entity_id: str) -> None:
        await self._store().reassign_decision(decision_id, to_entity_id)

    async def create_entity(self, entity: EntityWrite) -> None:
        await self._store().create_entity(entity)

    async def delete_entity_if_orphan(self, entity_id: str) -> bool:
        return await self._store().delete_entity_if_orphan(entity_id)

    async def set_document_topics(self, document_id: str, topic_ids: list[str]) -> None:
        await self._store().set_document_topics(document_id, topic_ids)

    # ── module-5: 검색 ─────────────────────────────────────────────────────
    async def link_entities(self, scope_key, phrases, embedding, topic_ids, limit):
        return await self._store().link_entities(
            scope_key, phrases, embedding, topic_ids, limit
        )

    async def seed_mentions(self, entity_ids, topic_ids):
        return await self._store().seed_mentions(entity_ids, topic_ids)

    async def find_paths(self, seed_ids, max_hops, hub_limit, limit):
        return await self._store().find_paths(seed_ids, max_hops, hub_limit, limit)

    async def chunks_in_scope(self, chunk_ids, topic_ids):
        return await self._store().chunks_in_scope(chunk_ids, topic_ids)

    # ── module-5b: 관리자 점검 ──────────────────────────────────────────────
    async def search_entities(self, query, type_, skip, limit):
        return await self._store().search_entities(query, type_, skip, limit)

    async def entity_detail(self, entity_id):
        return await self._store().entity_detail(entity_id)

    async def sample_chunks(self, kb_id, limit):
        return await self._store().sample_chunks(kb_id, limit)
