"""Neo4jGraphStore — Aura(neo4j+s://)·자체 호스팅(bolt://) 공용 어댑터.

Design Ref: graph-rag-foundation §3.2·D1-a — 주소만 바꾸면 전환된다(코드 분기 없음).
neo4j 드라이버 import 는 infrastructure/graph_rag/neo4j/ 에만 둔다.
드라이버 예외는 GraphBackendUnavailableError 로 바꿔 올린다.
"""

from __future__ import annotations

from typing import Any

from src.domain.graph_rag.exceptions import (
    GraphBackendUnavailableError,
    GraphEmbeddingDimMismatchError,
)
from src.domain.graph_rag.extraction import (
    REL_REFERS_TO,
    REL_RELATES,
    ChunkGraphWrite,
)
from src.domain.graph_rag.interfaces import GraphStorePort
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.graph_rag.neo4j import cypher

_DIM_KEY = "vector.dimensions"


def build_driver(
    uri: str, user: str, password: str, *, max_pool_size: int, connect_timeout_s: float
) -> Any:
    """앱 수명 싱글턴 드라이버 (app-lifetime-client-singleton)."""
    from neo4j import AsyncGraphDatabase

    return AsyncGraphDatabase.driver(
        uri,
        auth=(user, password),
        max_connection_pool_size=max_pool_size,
        connection_timeout=connect_timeout_s,
    )


class Neo4jGraphStore(GraphStorePort):
    def __init__(self, driver: Any, database: str, logger: LoggerInterface) -> None:
        self._driver = driver
        self._database = database
        self._logger = logger

    async def _query(self, statement: str, **params: Any) -> list[Any]:
        try:
            result = await self._driver.execute_query(
                statement, parameters_=params or None, database_=self._database
            )
        except Exception as e:  # noqa: BLE001 — 드라이버 예외를 도메인 예외로
            raise GraphBackendUnavailableError(f"{type(e).__name__}: {e}") from e
        return list(result.records)

    async def ping(self) -> None:
        try:
            await self._driver.verify_connectivity()
        except Exception as e:  # noqa: BLE001
            raise GraphBackendUnavailableError(f"{type(e).__name__}: {e}") from e

    async def counts(self) -> tuple[int, int]:
        nodes = await self._query(cypher.COUNT_NODES)
        rels = await self._query(cypher.COUNT_RELATIONSHIPS)
        return int(nodes[0]["c"]), int(rels[0]["c"])

    async def ensure_schema(self, embedding_dimensions: int) -> None:
        if not isinstance(embedding_dimensions, int) or embedding_dimensions <= 0:
            raise ValueError(f"invalid embedding dimensions: {embedding_dimensions!r}")
        for statement in cypher.SCHEMA_STATEMENTS:
            await self._query(statement)
        existing = await self._vector_index_dims()
        if existing is None:
            await self._query(
                cypher.VECTOR_INDEX_CREATE.format(dims=embedding_dimensions)
            )
            self._logger.info(
                "graph vector index created", dimensions=embedding_dimensions
            )
            return
        if existing != embedding_dimensions:
            raise GraphEmbeddingDimMismatchError(
                f"vector index has {existing} dims, "
                f"settings want {embedding_dimensions}"
            )

    async def _vector_index_dims(self) -> int | None:
        rows = await self._query(
            cypher.VECTOR_INDEX_SHOW, name=cypher.VECTOR_INDEX_NAME
        )
        if not rows:
            return None
        options = rows[0]["options"] or {}
        dims = (options.get("indexConfig") or {}).get(_DIM_KEY)
        return int(dims) if dims is not None else None

    async def aclose(self) -> None:
        await self._driver.close()

    # ── module-3: 적재 ──────────────────────────────────────────────────────

    async def extracted_chunk_ids(self, document_id: str, version: str) -> set[str]:
        rows = await self._query(
            cypher.EXTRACTED_CHUNKS, document_id=document_id, version=version
        )
        return {r["chunk_id"] for r in rows}

    async def delete_document(self, document_id: str) -> None:
        await self._query(cypher.DELETE_DOC_RELATES, document_id=document_id)
        await self._query(cypher.DELETE_DOC_CHUNKS, document_id=document_id)
        await self._query(cypher.DELETE_ORPHAN_ENTITIES)

    async def find_entity_id(
        self, scope_key: str, normalized_name: str, type_: str
    ) -> str | None:
        rows = await self._query(
            cypher.FIND_ENTITY,
            scope_key=scope_key,
            normalized=normalized_name,
            type=type_,
        )
        return rows[0]["id"] if rows else None

    async def write_chunk_graph(self, write: ChunkGraphWrite) -> None:
        params = _chunk_params(write)
        try:
            async with self._driver.session(database=self._database) as session:
                await session.execute_write(_write_chunk_tx, params)
        except Exception as e:  # noqa: BLE001
            raise GraphBackendUnavailableError(f"{type(e).__name__}: {e}") from e


def _chunk_params(write: ChunkGraphWrite) -> dict[str, Any]:
    unit = write.unit

    def _rels(kind: str) -> list[dict[str, Any]]:
        return [
            {
                "id": r.id,
                "source": r.source_entity_id,
                "target": r.target_entity_id,
                "type": r.type,
                "evidence_text": r.evidence_text,
                "source_decision_id": r.source_decision_id,
                "target_decision_id": r.target_decision_id,
            }
            for r in write.relations
            if r.kind == kind
        ]

    return {
        "chunk_id": unit.chunk_id,
        "document_id": unit.document_id,
        "kb_id": unit.kb_id,
        "collection_name": unit.collection_name,
        "version": write.extractor_version,
        "entities": [e.__dict__ for e in write.new_entities],
        "mentions": [m.__dict__ for m in write.mentions],
        "relates": _rels(REL_RELATES),
        "refers": _rels(REL_REFERS_TO),
    }


async def _write_chunk_tx(tx: Any, p: dict[str, Any]) -> None:
    """한 트랜잭션: 청크 → 새 엔티티 → 언급 → 관계. 실패하면 전체 롤백."""
    base = {
        k: p[k]
        for k in ("chunk_id", "document_id", "kb_id", "collection_name", "version")
    }
    await tx.run(cypher.WRITE_CHUNK, **base)
    if p["entities"]:
        await tx.run(cypher.WRITE_ENTITIES, entities=p["entities"])
    if p["mentions"]:
        await tx.run(cypher.WRITE_MENTIONS, mentions=p["mentions"], **base)
    if p["relates"]:
        await tx.run(cypher.WRITE_RELATES, relations=p["relates"], **base)
    if p["refers"]:
        await tx.run(cypher.WRITE_REFERS_TO, relations=p["refers"], **base)
