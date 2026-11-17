"""Neo4j 쓰기 파라미터·RuntimeGraphStore 단위 + 실Neo4j 쓰기/삭제 왕복(-m neo4j)."""
import os
import uuid
from unittest.mock import MagicMock

import pytest
from src.api.graph_rag_runtime_store import RuntimeGraphStore
from src.domain.graph_rag.exceptions import GraphBackendUnavailableError
from src.domain.graph_rag.extraction import (
    REL_REFERS_TO,
    REL_RELATES,
    ChunkGraphWrite,
    ChunkUnit,
    EntityWrite,
    MentionWrite,
    RelationWrite,
)
from src.infrastructure.graph_rag.neo4j.store import (
    Neo4jGraphStore,
    _chunk_params,
    build_driver,
)

from tests.application.graph_rag.fakes import FakeStore


def _write(doc="doc-1", chunk="p1"):
    e1, e2, e3 = (str(uuid.uuid4()) for _ in range(3))
    return ChunkGraphWrite(
        unit=ChunkUnit(chunk_id=chunk, document_id=doc, kb_id="kb", collection_name="c",
                       content="x", chunk_index=0),
        extractor_version="v1",
        new_entities=tuple(
            EntityWrite(id=i, scope_key="test", name=n, normalized_name=n, type=t,
                        description="")
            for i, n, t in ((e1, "a상품", "상품"), (e2, "개인", "대상"), (e3, "제3조", "조문"))
        ),
        mentions=(MentionWrite(e1, "d1"), MentionWrite(e2, "d2"), MentionWrite(e3, "d3")),
        relations=(
            RelationWrite("r1", REL_RELATES, e1, e2, "적용대상", "근거", "d1", "d2"),
            RelationWrite("r2", REL_REFERS_TO, e1, e3, "참조", "근거", "d1", "d3"),
        ),
    )


def test_chunk_params_split_relation_kinds():
    p = _chunk_params(_write())
    assert [r["id"] for r in p["relates"]] == ["r1"]
    assert [r["id"] for r in p["refers"]] == ["r2"]
    assert len(p["entities"]) == 3 and len(p["mentions"]) == 3
    assert p["version"] == "v1" and p["chunk_id"] == "p1"


@pytest.mark.asyncio
async def test_runtime_store_delegates_and_reports_unavailable():
    current = {"store": None}
    proxy = RuntimeGraphStore(lambda: current["store"])
    assert proxy.available() is False
    with pytest.raises(GraphBackendUnavailableError):
        await proxy.extracted_chunk_ids("d", "v1")
    current["store"] = FakeStore()
    assert proxy.available() is True
    await proxy.write_chunk_graph(_write())
    assert await proxy.extracted_chunk_ids("doc-1", "v1") == {"p1"}


_URI = os.environ.get("NEO4J_URI")


@pytest.mark.neo4j
@pytest.mark.skipif(not _URI, reason="NEO4J_URI not set")
@pytest.mark.asyncio
async def test_live_write_resume_and_delete_roundtrip():
    driver = build_driver(
        _URI, os.environ.get("NEO4J_USER", "neo4j"), os.environ["NEO4J_PASSWORD"],
        max_pool_size=2, connect_timeout_s=10,
    )
    store = Neo4jGraphStore(driver, os.environ.get("NEO4J_DATABASE", "neo4j"),
                            MagicMock())
    doc = f"test-doc-{uuid.uuid4()}"
    try:
        w = _write(doc=doc, chunk=f"chunk-{uuid.uuid4()}")
        await store.write_chunk_graph(w)
        await store.write_chunk_graph(w)  # 같은 쓰기 재실행 — 중복 없어야 함
        assert await store.extracted_chunk_ids(doc, "v1") == {w.unit.chunk_id}
        found = await store.find_entity_id("test", "a상품", "상품")
        assert found == w.new_entities[0].id
    finally:
        await store.delete_document(doc)
        assert await store.extracted_chunk_ids(doc, "v1") == set()
        assert await store.find_entity_id("test", "a상품", "상품") is None
        await store.aclose()
