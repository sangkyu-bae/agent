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


@pytest.mark.neo4j
@pytest.mark.skipif(not _URI, reason="NEO4J_URI not set")
@pytest.mark.asyncio
async def test_live_candidates_alias_reassign_and_orphan():
    """module-4: 벡터·별칭 후보 검색, 판정 이동(검토 거절), 고아 정리."""
    from src.domain.graph_rag.extraction import AliasWrite

    dims = int(os.environ.get("GRAPH_ENTITY_EMBEDDING_DIMENSIONS", "512"))
    driver = build_driver(
        _URI, os.environ.get("NEO4J_USER", "neo4j"), os.environ["NEO4J_PASSWORD"],
        max_pool_size=2, connect_timeout_s=10,
    )
    store = Neo4jGraphStore(driver, os.environ.get("NEO4J_DATABASE", "neo4j"),
                            MagicMock())
    scope = f"test-{uuid.uuid4()}"
    doc = f"test-doc-{uuid.uuid4()}"
    vec = [1.0] + [0.0] * (dims - 1)
    near = [0.98, 0.2] + [0.0] * (dims - 2)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    unit = ChunkUnit(chunk_id=f"chunk-{uuid.uuid4()}", document_id=doc, kb_id="kb",
                     collection_name="c", content="x", chunk_index=0)
    try:
        await store.ensure_schema(dims)
        await store.write_chunk_graph(ChunkGraphWrite(
            unit=unit, extractor_version="v2",
            new_entities=(
                EntityWrite(a, scope, "A상품", "a상품", "상품", "", tuple(vec)),
                EntityWrite(b, scope, "B상품", "b상품", "상품", ""),
            ),
            mentions=(MentionWrite(a, "dec-a"), MentionWrite(b, "dec-b")),
            relations=(RelationWrite("rel-1", REL_RELATES, a, b, "포함", "근거",
                                     "dec-a", "dec-b"),),
            aliases=(AliasWrite(a, scope, "에이상품", "에이상품"),),
        ))
        exact = await store.find_candidates(scope, "a상품", None, 5)
        assert [(c.entity_id, c.match) for c in exact] == [(a, "exact")]
        alias = await store.find_candidates(scope, "에이상품", None, 5)
        assert [(c.entity_id, c.match) for c in alias] == [(a, "alias")]
        # 벡터 인덱스 반영은 비동기라 잠시 기다린다
        import asyncio as _aio
        for _ in range(20):
            by_vec = await store.find_candidates(scope, "없는이름", near, 5)
            if by_vec:
                break
            await _aio.sleep(0.5)
        assert by_vec and by_vec[0].entity_id == a and by_vec[0].match == "vector"
        assert by_vec[0].similarity > 0.9
        # 검토 거절: dec-b 를 새 엔티티 c 로 분리 → b 는 고아가 되어 삭제
        c = str(uuid.uuid4())
        await store.create_entity(EntityWrite(c, scope, "B'상품", "b'상품", "상품", ""))
        await store.reassign_decision("dec-b", c)
        assert await store.delete_entity_if_orphan(b) is True
        assert await store.delete_entity_if_orphan(a) is False  # 언급이 남아 있음
        rel = await store._query(
            "MATCH (x:Entity)-[r:RELATES {id: 'rel-1'}]->(y:Entity) "
            "RETURN x.id AS s, y.id AS t"
        )
        assert (rel[0]["s"], rel[0]["t"]) == (a, c)  # 관계 끝점도 옮겨졌다
    finally:
        await store.delete_document(doc)
        await store._query("MATCH (e:Entity {scope_key: $s}) DETACH DELETE e", s=scope)
        await store._query("MATCH (x:Alias {scope_key: $s}) DETACH DELETE x", s=scope)
        await store.aclose()
