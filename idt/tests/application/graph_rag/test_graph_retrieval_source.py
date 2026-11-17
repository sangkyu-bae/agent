"""GraphRetrievalSource — 단계·범위·연결·탐색·권한 재조회 (Design §2.2 검색, FR-12~14·29)."""
from __future__ import annotations

import asyncio
import dataclasses
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.graph_rag.retrieval.source import GraphRetrievalSource
from src.domain.extension_hooks.events import SupplementalGrant, SupplementalQuery
from src.domain.graph_rag.exceptions import GraphBackendUnavailableError
from src.domain.graph_rag.retrieval import (
    HUB_DEGREE_LIMIT,
    LinkedEntity,
    PathHit,
    QueryScope,
)
from src.domain.graph_rag.value_objects import GraphRagSettings, RolloutStage
from src.domain.hybrid_search.schemas import HybridSearchResult

from tests.application.graph_rag.fakes import FakeReader


def _settings(**over):
    base = dataclasses.replace(GraphRagSettings.defaults(),
                               rollout_stage=RolloutStage.ADMIN_ONLY)
    return dataclasses.replace(base, **over)


def _query(admin=True, **over):
    base = dict(query="운전자금대출 한도는?", top_k=5, collection_name="col",
                es_index="idx", hard_filter={"kb_id": "kb1"},
                lenient_filter={"department": "d1"},
                grant=SupplementalGrant(caller_is_admin=admin), request_id="r")
    base.update(over)
    return SupplementalQuery(**base)


def _hit(cid):
    return HybridSearchResult(id=cid, content=f"{cid} 본문", score=0.0, bm25_rank=None,
                              bm25_score=None, vector_rank=None, vector_score=None,
                              source="graph", metadata={"document_id": "doc"})


def _make(settings=None, scope=None, linked=None, paths=(), mentions=None,
          in_scope=None, fetched=None):
    store = MagicMock()
    linked = [LinkedEntity("e1", "운전자금대출 한도", "용어", "exact", 1.0)] \
        if linked is None else linked
    store.link_entities = AsyncMock(return_value=linked)
    store.seed_mentions = AsyncMock(return_value=mentions or {"c1": 1})
    store.find_paths = AsyncMock(return_value=list(paths))
    store.chunks_in_scope = AsyncMock(
        side_effect=lambda ids, topics: set(ids) if in_scope is None else in_scope)
    fetcher = MagicMock()
    fetcher.fetch = AsyncMock(
        side_effect=lambda ids, **kw: [_hit(c) for c in ids
                                       if fetched is None or c in fetched])
    router = MagicMock()
    router.route = AsyncMock(return_value=scope or QueryScope(reason="no_topics"))
    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=[[0.1, 0.2]])
    morph = MagicMock()
    morph.extract_nouns.return_value = ["운전", "자금", "대출", "한도"]
    src = GraphRetrievalSource(
        reader=FakeReader(settings or _settings()), store=store, embedder=embedder,
        morph=morph, router=router, fetcher=fetcher, logger=MagicMock(),
    )
    return src, store, fetcher, router


@pytest.mark.asyncio
async def test_happy_path_links_traverses_and_fetches_with_tool_filters():
    paths = [PathHit(("운전자금대출 한도", "연매출액의 30%"), ("한도",), ("c2",))]
    src, store, fetcher, _ = _make(paths=paths,
                                   scope=QueryScope(("t-loan",), ("여신관리",), "llm"))
    result = await src.retrieve(_query())
    assert result.skip_reason is None and result.label == "graph"
    assert [h.id for h in result.hits] == ["c1", "c2"]  # 씨앗 언급 1.0 > 근거 0.5
    assert result.hits[0].score > result.hits[1].score
    assert result.weight == _settings().graph_rrf_weight
    phrases = store.link_entities.call_args.args[1]
    assert "운전자금대출" in phrases
    # 연결은 주제 판정과 동시에(범위 없이), 범위는 근거 청크에서 건다
    assert store.link_entities.call_args.args[3] is None
    assert store.chunks_in_scope.call_args.args[1] == ("t-loan",)
    assert store.find_paths.call_args.args[2] == HUB_DEGREE_LIMIT
    kw = fetcher.fetch.call_args.kwargs
    assert (kw["hard_filter"], kw["lenient_filter"], kw["collection_name"],
            kw["es_index"]) == ({"kb_id": "kb1"}, {"department": "d1"}, "col", "idx")


@pytest.mark.asyncio
@pytest.mark.parametrize("stage,admin,reason", [
    (RolloutStage.OFF, True, "stage_off"),
    (RolloutStage.ADMIN_ONLY, False, "grant_not_admin"),
])
async def test_stage_gate(stage, admin, reason):
    src, store, _, router = _make(settings=_settings(rollout_stage=stage))
    result = await src.retrieve(_query(admin=admin))
    assert result.skip_reason == reason and result.hits == []
    router.route.assert_not_called()


@pytest.mark.asyncio
async def test_no_evidence_in_scope_falls_back_to_unscoped():
    src, *_ = _make(scope=QueryScope(("t-x",), ("x",), "jev"), in_scope=set())
    trace = await src.search_trace(_query(), _settings())
    assert trace.scope.topic_ids is None and trace.scope.reason == "no_chunk_in_scope"
    assert [h.id for h in trace.hits] == ["c1"]


@pytest.mark.asyncio
async def test_routing_and_linking_run_concurrently():
    import time

    src, store, _, router = _make(settings=_settings(retrieval_timeout_ms=5000))

    async def slow_route(*a, **k):
        await asyncio.sleep(0.3)
        return QueryScope(reason="no_topics")

    async def slow_link(*a, **k):
        await asyncio.sleep(0.3)
        return [LinkedEntity("e1", "a", "용어", "exact", 1.0)]
    router.route.side_effect = slow_route
    store.link_entities.side_effect = slow_link
    started = time.perf_counter()
    await src.search_trace(_query(), _settings(retrieval_timeout_ms=5000))
    assert time.perf_counter() - started < 0.5  # 직렬이면 0.6초 이상


@pytest.mark.asyncio
async def test_no_entity_at_all_skips():
    src, *_ = _make(linked=[])
    result = await src.retrieve(_query())
    assert result.skip_reason == "no_entity"


@pytest.mark.asyncio
async def test_permission_filter_drops_chunks_and_counts_them():
    paths = [PathHit(("a", "b"), ("r",), ("c2",))]
    src, *_ = _make(paths=paths, fetched={"c2"})
    trace = await src.search_trace(_query(), _settings())
    assert [h.id for h in trace.hits] == ["c2"] and trace.filtered_out == 1


@pytest.mark.asyncio
async def test_out_of_scope_evidence_chunks_are_dropped():
    paths = [PathHit(("a", "b"), ("r",), ("c-other",))]
    src, *_ = _make(paths=paths, in_scope={"c1"},
                    scope=QueryScope(("t-loan",), ("여신",), "jev"))
    trace = await src.search_trace(_query(), _settings())
    assert [h.id for h in trace.hits] == ["c1"]


@pytest.mark.asyncio
async def test_backend_down_and_errors_skip_without_raising():
    src, store, *_ = _make()
    store.link_entities.side_effect = GraphBackendUnavailableError("down")
    assert (await src.retrieve(_query())).skip_reason == "backend_unavailable"
    store.link_entities.side_effect = RuntimeError("boom")
    assert (await src.retrieve(_query())).skip_reason == "error"


@pytest.mark.asyncio
async def test_overall_timeout_skips():
    src, store, *_ = _make(settings=_settings(retrieval_timeout_ms=100))

    async def slow(*a, **k):
        await asyncio.sleep(1)
    store.link_entities.side_effect = slow
    assert (await src.retrieve(_query())).skip_reason == "timeout"


@pytest.mark.asyncio
async def test_slow_topic_routing_searches_without_scope():
    src, store, _, router = _make(settings=_settings(retrieval_timeout_ms=400))

    async def slow(*a, **k):
        await asyncio.sleep(1)
        return QueryScope(("t",), ("t",), "llm")
    router.route.side_effect = slow
    trace = await src.search_trace(_query(), _settings(retrieval_timeout_ms=400))
    assert trace.scope.reason == "route_timeout"
    assert store.link_entities.call_args.args[3] is None
    assert trace.hits


@pytest.mark.asyncio
async def test_hits_limited_to_top_k():
    paths = [PathHit(("a", "b"), ("r",), (f"c{i}",)) for i in range(2, 12)]
    src, *_ = _make(paths=paths)
    result = await src.retrieve(_query(top_k=3))
    assert len(result.hits) == 3
