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


@pytest.mark.neo4j
@pytest.mark.skipif(not _URI, reason="NEO4J_URI not set")
@pytest.mark.asyncio
async def test_live_set_document_topics_copies_ids_to_all_chunks():
    """module-4b: 문서의 모든 청크에 topic_ids 복사, 다른 문서는 그대로."""
    driver = build_driver(
        _URI, os.environ.get("NEO4J_USER", "neo4j"), os.environ["NEO4J_PASSWORD"],
        max_pool_size=2, connect_timeout_s=10,
    )
    store = Neo4jGraphStore(driver, os.environ.get("NEO4J_DATABASE", "neo4j"),
                            MagicMock())
    doc, other = f"test-doc-{uuid.uuid4()}", f"test-doc-{uuid.uuid4()}"

    def _w(d, i):
        unit = ChunkUnit(chunk_id=f"chunk-{uuid.uuid4()}", document_id=d, kb_id="kb",
                         collection_name="c", content="x", chunk_index=i)
        return ChunkGraphWrite(unit=unit, extractor_version="v3", new_entities=(),
                               mentions=(), relations=())
    try:
        for w in (_w(doc, 0), _w(doc, 1), _w(other, 0)):
            await store.write_chunk_graph(w)
        await store.set_document_topics(doc, ["t-loan", "t-corp"])
        rows = await store._query(
            "MATCH (c:Chunk) WHERE c.document_id IN [$a, $b] "
            "RETURN c.document_id AS d, c.topic_ids AS t", a=doc, b=other)
        got = sorted((r["d"] == doc, tuple(r["t"] or ())) for r in rows)
        assert got == [(False, ()), (True, ("t-loan", "t-corp")),
                       (True, ("t-loan", "t-corp"))]
    finally:
        await store.delete_document(doc)
        await store.delete_document(other)
        await store.aclose()


@pytest.mark.neo4j
@pytest.mark.skipif(not _URI, reason="NEO4J_URI not set")
@pytest.mark.asyncio
async def test_live_link_traverse_hub_and_scope():
    """module-5: 연결(정확·별칭·벡터)·경로·허브 경유 금지·주제 범위."""
    from src.domain.graph_rag.extraction import AliasWrite
    from src.domain.graph_rag.retrieval import HUB_DEGREE_LIMIT

    dims = int(os.environ.get("GRAPH_ENTITY_EMBEDDING_DIMENSIONS", "512"))
    driver = build_driver(
        _URI, os.environ.get("NEO4J_USER", "neo4j"), os.environ["NEO4J_PASSWORD"],
        max_pool_size=2, connect_timeout_s=10,
    )
    store = Neo4jGraphStore(driver, os.environ.get("NEO4J_DATABASE", "neo4j"),
                            MagicMock())
    scope, doc = f"test-{uuid.uuid4()}", f"test-doc-{uuid.uuid4()}"
    ids = {k: str(uuid.uuid4()) for k in ("a", "b", "c", "hub", "far")}
    leaves = [str(uuid.uuid4()) for _ in range(HUB_DEGREE_LIMIT + 1)]
    vec = [1.0] + [0.0] * (dims - 1)
    unit = ChunkUnit(chunk_id=f"chunk-{uuid.uuid4()}", document_id=doc, kb_id="kb",
                     collection_name="c", content="x", chunk_index=0)

    def ent(key, name, emb=None):
        return EntityWrite(key, scope, name, name.lower(), "용어", "", emb)

    def rel(i, s, t):
        return RelationWrite(f"rel-{scope}-{i}", REL_RELATES, s, t, "포함", "근거",
                             "dec", "dec")
    rels = [rel(0, ids["a"], ids["b"]), rel(1, ids["b"], ids["c"]),
            rel(2, ids["a"], ids["hub"]), rel(3, ids["hub"], ids["far"])]
    rels += [rel(10 + i, ids["hub"], lf) for i, lf in enumerate(leaves)]
    try:
        await store.ensure_schema(dims)
        await store.write_chunk_graph(ChunkGraphWrite(
            unit=unit, extractor_version="v3",
            new_entities=(ent(ids["a"], "A상품", tuple(vec)), ent(ids["b"], "B조건"),
                          ent(ids["c"], "C기준"), ent(ids["hub"], "규정집"),
                          ent(ids["far"], "먼개념"),
                          *[ent(lf, f"잎{i}") for i, lf in enumerate(leaves)]),
            mentions=(MentionWrite(ids["a"], "dec-a"),),
            relations=tuple(rels),
            aliases=(AliasWrite(ids["a"], scope, "에이상품", "에이상품"),),
        ))
        await store.set_document_topics(doc, ["t-loan"])

        exact = await store.link_entities(scope, ["a상품"], None, None, 5)
        assert [(e.id, e.via) for e in exact] == [(ids["a"], "exact")]
        alias = await store.link_entities(scope, ["에이상품"], None, ("t-loan",), 5)
        assert [(e.id, e.via) for e in alias] == [(ids["a"], "alias")]
        assert await store.link_entities(scope, ["a상품"], None, ("t-other",), 5) == []
        import asyncio as _aio
        for _ in range(20):
            by_vec = await store.link_entities(scope, [], vec, None, 5)
            if by_vec:
                break
            await _aio.sleep(0.5)
        assert by_vec[0].id == ids["a"] and by_vec[0].via == "vector"

        mentions = await store.seed_mentions([ids["a"]], ("t-loan",))
        assert mentions == {unit.chunk_id: 1}
        assert await store.seed_mentions([ids["a"]], ("t-other",)) == {}

        paths = await store.find_paths([ids["a"]], 2, HUB_DEGREE_LIMIT, 200)
        ends = {p.names[-1] for p in paths}
        assert {"B조건", "C기준", "규정집"} <= ends  # 허브까지는 간다
        assert "먼개념" not in ends  # 허브를 지나가지는 않는다
        assert all(p.evidence_chunk_ids[0] == unit.chunk_id for p in paths)

        assert await store.chunks_in_scope([unit.chunk_id, "nope"], ("t-loan",)) == {
            unit.chunk_id}
        assert await store.chunks_in_scope([unit.chunk_id], ("t-other",)) == set()

        # ① 범위 안 씨앗 고르기 — 범위 청크에 언급된 엔티티만
        assert await store.entities_in_scope(
            [ids["a"], ids["b"], ids["far"]], ("t-loan",)) == {ids["a"]}
        assert await store.entities_in_scope([ids["a"]], ("t-other",)) == set()
        # ② 관계에도 문서 주제가 복사되고, 범위 밖 관계는 타지 않는다
        tagged = await store._query(
            "MATCH ()-[r:RELATES {document_id: $d}]->() "
            "RETURN count(r) AS n, all(x IN collect(r.topic_ids) "
            "WHERE x = ['t-loan']) AS ok", d=doc)
        assert tagged[0]["n"] == len(rels) and tagged[0]["ok"]
        scoped = await store.find_paths([ids["a"]], 2, HUB_DEGREE_LIMIT, 200,
                                        topic_ids=("t-loan",))
        assert {p.names[-1] for p in scoped} == ends
        assert await store.find_paths([ids["a"]], 2, HUB_DEGREE_LIMIT, 200,
                                       topic_ids=("t-other",)) == []
    finally:
        await store.delete_document(doc)
        await store._query("MATCH (e:Entity {scope_key: $s}) DETACH DELETE e", s=scope)
        await store._query("MATCH (x:Alias {scope_key: $s}) DETACH DELETE x", s=scope)
        await store.aclose()


@pytest.mark.neo4j
@pytest.mark.skipif(not _URI, reason="NEO4J_URI not set")
@pytest.mark.asyncio
async def test_live_entity_search_detail_and_chunk_sample():
    """module-5b: 엔티티 목록(값 엔티티 제외)·상세·정합성 표본."""
    from src.domain.graph_rag.extraction import AliasWrite

    driver = build_driver(
        _URI, os.environ.get("NEO4J_USER", "neo4j"), os.environ["NEO4J_PASSWORD"],
        max_pool_size=2, connect_timeout_s=10,
    )
    store = Neo4jGraphStore(driver, os.environ.get("NEO4J_DATABASE", "neo4j"),
                            MagicMock())
    tag = uuid.uuid4().hex[:8]
    doc, kb = f"test-doc-{tag}", f"kb-{tag}"
    unit = ChunkUnit(chunk_id=f"chunk-{tag}", document_id=doc, kb_id=kb,
                     collection_name="c", content="x", chunk_index=0)
    a, b, v = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    try:
        await store.write_chunk_graph(ChunkGraphWrite(
            unit=unit, extractor_version="v3",
            new_entities=(
                EntityWrite(a, "global", f"점검상품{tag}", f"점검상품{tag}", "상품", "설명"),
                EntityWrite(b, "global", f"점검대상{tag}", f"점검대상{tag}", "대상", ""),
                EntityWrite(v, "global", "30%", f"{unit.chunk_id}::점검{tag}", "기타", ""),
            ),
            mentions=(MentionWrite(a, "dec-a"), MentionWrite(v, "dec-v")),
            relations=(RelationWrite(f"rel-{tag}", REL_RELATES, a, b, "적용대상", "근거문장",
                                     "dec-a", "dec-b"),),
            aliases=(AliasWrite(a, "global", f"별칭{tag}", f"별칭{tag}"),),
        ))
        items, total = await store.search_entities(f"점검", None, 0, 100)
        names = {e.name for e in items}
        assert f"점검상품{tag}" in names and "30%" not in names  # 값 엔티티 제외
        only, n = await store.search_entities(f"점검상품{tag}", "상품", 0, 10)
        assert n == 1 and only[0].mention_count == 1 and only[0].relation_count == 1

        detail = await store.entity_detail(a)
        assert detail.aliases == [f"별칭{tag}"]
        rel = detail.relations[0]
        assert (rel.direction, rel.type, rel.other_id, rel.evidence_chunk_id,
                rel.evidence_text) == ("out", "적용대상", b, unit.chunk_id, "근거문장")
        assert [m.chunk_id for m in detail.mentions] == [unit.chunk_id]
        assert (await store.entity_detail(b)).relations[0].direction == "in"
        assert await store.entity_detail("nope") is None

        refs = await store.sample_chunks(kb, 10)
        assert [(r.chunk_id, r.document_id) for r in refs] == [(unit.chunk_id, doc)]
    finally:
        await store.delete_document(doc)
        await store._query("MATCH (e:Entity) WHERE e.id IN $ids DETACH DELETE e",
                           ids=[a, b, v])
        await store._query("MATCH (x:Alias {normalized: $n}) DETACH DELETE x",
                           n=f"별칭{tag}")
        await store.aclose()
