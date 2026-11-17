"""Neo4jGraphStore — 단위(가짜 드라이버) + 통합(-m neo4j, NEO4J_URI 필요)."""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from src.domain.graph_rag.exceptions import (
    GraphBackendUnavailableError,
    GraphEmbeddingDimMismatchError,
)
from src.domain.graph_rag.policies import is_external_graph_uri
from src.infrastructure.graph_rag.neo4j import cypher
from src.infrastructure.graph_rag.neo4j.store import Neo4jGraphStore, build_driver


class _Driver:
    def __init__(self, *, existing_dims=None, fail=False):
        self.statements = []
        self._dims = existing_dims
        self._fail = fail
        self.closed = False

    async def execute_query(self, statement, parameters_=None, database_=None):
        if self._fail:
            raise ConnectionError("aura paused")
        self.statements.append(statement)
        if statement == cypher.VECTOR_INDEX_SHOW:
            rows = [] if self._dims is None else [
                {"options": {"indexConfig": {"vector.dimensions": self._dims}}}
            ]
            return SimpleNamespace(records=rows)
        if statement in (cypher.COUNT_NODES, cypher.COUNT_RELATIONSHIPS):
            return SimpleNamespace(records=[{"c": 7}])
        return SimpleNamespace(records=[])

    async def verify_connectivity(self):
        if self._fail:
            raise ConnectionError("aura paused")

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_ensure_schema_creates_vector_index_when_missing():
    driver = _Driver()
    await Neo4jGraphStore(driver, "neo4j", MagicMock()).ensure_schema(512)
    created = [s for s in driver.statements if s.startswith("CREATE VECTOR INDEX")]
    assert len(created) == 1 and "`vector.dimensions`: 512" in created[0]
    assert all(s in driver.statements for s in cypher.SCHEMA_STATEMENTS)


@pytest.mark.asyncio
async def test_ensure_schema_same_dims_is_idempotent():
    driver = _Driver(existing_dims=512)
    await Neo4jGraphStore(driver, "neo4j", MagicMock()).ensure_schema(512)
    assert not any(s.startswith("CREATE VECTOR INDEX") for s in driver.statements)


@pytest.mark.asyncio
async def test_ensure_schema_dim_mismatch_raises():
    driver = _Driver(existing_dims=1536)
    with pytest.raises(GraphEmbeddingDimMismatchError):
        await Neo4jGraphStore(driver, "neo4j", MagicMock()).ensure_schema(512)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [0, -1, "512", 3.5])
async def test_ensure_schema_rejects_bad_dims(bad):
    with pytest.raises(ValueError):
        await Neo4jGraphStore(_Driver(), "neo4j", MagicMock()).ensure_schema(bad)


@pytest.mark.asyncio
async def test_driver_errors_become_backend_unavailable():
    store = Neo4jGraphStore(_Driver(fail=True), "neo4j", MagicMock())
    with pytest.raises(GraphBackendUnavailableError):
        await store.ping()
    with pytest.raises(GraphBackendUnavailableError):
        await store.counts()


@pytest.mark.asyncio
async def test_counts_and_close():
    driver = _Driver()
    store = Neo4jGraphStore(driver, "neo4j", MagicMock())
    assert await store.counts() == (7, 7)
    await store.aclose()
    assert driver.closed


@pytest.mark.parametrize("uri, external", [
    ("neo4j+s://abcd1234.databases.neo4j.io", True),
    ("neo4j+s://abcd1234.databases.neo4j.io:7687", True),
    ("bolt://localhost:7687", False),
    ("neo4j://graph.internal:7687", False),
    (None, False), ("", False), ("not a uri", False),
])
def test_is_external_graph_uri(uri, external):
    assert is_external_graph_uri(uri) is external


# ── 통합: 실제 Neo4j(로컬 또는 Aura) — pytest -m neo4j ───────────────────────

_URI = os.environ.get("NEO4J_URI")


@pytest.mark.neo4j
@pytest.mark.skipif(not _URI, reason="NEO4J_URI not set")
@pytest.mark.asyncio
async def test_live_ping_schema_counts():
    driver = build_driver(
        _URI, os.environ.get("NEO4J_USER", "neo4j"), os.environ["NEO4J_PASSWORD"],
        max_pool_size=2, connect_timeout_s=10,
    )
    store = Neo4jGraphStore(
        driver, os.environ.get("NEO4J_DATABASE", "neo4j"), MagicMock()
    )
    try:
        await store.ping()
        dims = int(os.environ.get("GRAPH_ENTITY_EMBEDDING_DIMENSIONS", "512"))
        await store.ensure_schema(dims)
        await store.ensure_schema(dims)  # 멱등
        nodes, rels = await store.counts()
        assert nodes >= 0 and rels >= 0
    finally:
        await store.aclose()
