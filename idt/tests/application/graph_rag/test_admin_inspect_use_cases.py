"""관리자 점검·검색 테스트 유스케이스 (Design §4.1·§4.2, FR-16, SC-2)."""
from __future__ import annotations

import dataclasses
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.graph_rag.admin.inspect_use_case import InspectUseCase
from src.application.graph_rag.admin.search_test_use_case import SearchTestUseCase
from src.domain.graph_rag.exceptions import GraphStageOffError
from src.domain.graph_rag.inspection import (
    EntityDetail,
    EntitySummary,
    GraphChunkRef,
    MentionView,
)
from src.domain.graph_rag.retrieval import GraphSearchTrace
from src.domain.graph_rag.value_objects import (
    MAX_RETRIEVAL_TIMEOUT_MS,
    GraphRagSettings,
    RolloutStage,
)
from src.domain.hybrid_search.schemas import HybridSearchResult

from tests.application.graph_rag.fakes import FakeReader


def _settings(stage=RolloutStage.ADMIN_ONLY):
    return dataclasses.replace(GraphRagSettings.defaults(), rollout_stage=stage)


def _hit(cid, source="both"):
    return HybridSearchResult(id=cid, content=f"{cid} 본문 " * 50, score=0.1,
                              bm25_rank=1, bm25_score=1.0, vector_rank=1,
                              vector_score=0.9, source=source, metadata={})


def _inspect(store, fetched=(), stage=RolloutStage.ADMIN_ONLY):
    fetcher = MagicMock()
    fetcher.fetch = AsyncMock(return_value=[_hit(c) for c in fetched])
    return InspectUseCase(reader=FakeReader(_settings(stage)), store=store,
                          fetcher=fetcher, logger=MagicMock()), fetcher


@pytest.mark.asyncio
async def test_entities_paging_is_clamped_and_query_trimmed():
    store = MagicMock()
    store.search_entities = AsyncMock(return_value=([], 0))
    uc, _ = _inspect(store)
    await uc.entities(query="  여신 ", type_="", page=0, size=999)
    assert store.search_entities.call_args.args == ("여신", None, 0, 100)
    await uc.entities(query="", type_="상품", page=3, size=10)
    assert store.search_entities.call_args.args == (None, "상품", 20, 10)


@pytest.mark.asyncio
async def test_entity_detail_adds_mention_previews():
    entity = EntitySummary("e1", "A상품", "상품", "", 1, 2)
    store = MagicMock()
    store.entity_detail = AsyncMock(return_value=EntityDetail(
        entity=entity, mentions=[MentionView("c1", "doc", "d1"),
                                 MentionView("c9", "doc", "d2")]))
    uc, fetcher = _inspect(store, fetched=["c1"])
    detail = await uc.entity("e1", "r")
    assert len(detail.mentions[0].preview) == 200 and detail.mentions[1].preview == ""
    assert fetcher.fetch.call_args.kwargs["hard_filter"] == {}


@pytest.mark.asyncio
async def test_missing_entity_returns_none():
    store = MagicMock()
    store.entity_detail = AsyncMock(return_value=None)
    uc, _ = _inspect(store)
    assert await uc.entity("nope", "r") is None


@pytest.mark.asyncio
async def test_integrity_reports_chunks_missing_from_es():
    store = MagicMock()
    store.sample_chunks = AsyncMock(return_value=[
        GraphChunkRef("c1", "doc-a"), GraphChunkRef("c2", "doc-b"),
        GraphChunkRef("c3", "doc-b")])
    uc, _ = _inspect(store, fetched=["c1"])
    report = await uc.integrity(kb_id="kb1", sample=99999, request_id="r")
    assert store.sample_chunks.call_args.args == ("kb1", 2000)
    assert (report.checked, report.missing) == (3, 2)
    assert report.missing_chunk_ids == ("c2", "c3")
    assert report.missing_document_ids == ("doc-b",)


@pytest.mark.asyncio
async def test_stage_off_blocks_inspection():
    uc, _ = _inspect(MagicMock(), stage=RolloutStage.OFF)
    with pytest.raises(GraphStageOffError):
        await uc.entities(query=None, type_=None, page=1, size=10)
    with pytest.raises(GraphStageOffError):
        await uc.integrity(kb_id=None, sample=10, request_id="r")


def _search_uc(trace, hybrid=None, hybrid_exc=None, factory=True,
               stage=RolloutStage.ADMIN_ONLY):
    source = MagicMock()
    source.search_trace = AsyncMock(return_value=trace)
    uc_hybrid = MagicMock()
    uc_hybrid.execute = AsyncMock(
        side_effect=hybrid_exc,
        return_value=MagicMock(results=hybrid or []))
    made = []

    def _factory():
        made.append(1)
        return uc_hybrid
    uc = SearchTestUseCase(reader=FakeReader(_settings(stage)), source=source,
                           hybrid_factory=_factory if factory else None,
                           logger=MagicMock())
    return uc, source, uc_hybrid, made


@pytest.mark.asyncio
async def test_search_test_runs_graph_hybrid_and_fuses():
    trace = GraphSearchTrace(hits=[_hit("g1", "graph"), _hit("a", "graph")])
    uc, source, hybrid, made = _search_uc(trace, hybrid=[_hit("a"), _hit("b")])
    result = await uc.run(query="질문", kb_id="kb1", collection_name=None, top_k=5,
                          max_hops=2, request_id="r")
    sq, settings = source.search_trace.call_args.args
    assert sq.hard_filter == {"kb_id": "kb1"} and sq.grant.caller_is_admin
    assert settings.retrieval_timeout_ms == MAX_RETRIEVAL_TIMEOUT_MS
    assert source.search_trace.call_args.kwargs["max_hops"] == 2
    assert hybrid.execute.call_args.args[0].metadata_filter == {"kb_id": "kb1"}
    sources = {h.id: h.source for h in result.fused_hits}
    assert sources["a"] == "both+graph" and sources["g1"] == "graph"
    assert "hybrid" in result.trace.timings_ms
    await uc.run(query="또", kb_id=None, collection_name=None, top_k=5, max_hops=None,
                 request_id="r")
    assert made == [1]  # 하이브리드는 한 번만 만든다


@pytest.mark.asyncio
async def test_search_test_hybrid_failure_keeps_graph_result():
    trace = GraphSearchTrace(hits=[_hit("g1", "graph")])
    uc, *_ = _search_uc(trace, hybrid_exc=RuntimeError("qdrant down"))
    result = await uc.run(query="q", kb_id=None, collection_name=None, top_k=5,
                          max_hops=None, request_id="r")
    assert result.hybrid_error.startswith("RuntimeError")
    assert [h.id for h in result.fused_hits] == ["g1"]


@pytest.mark.asyncio
async def test_search_test_stage_off():
    uc, *_ = _search_uc(GraphSearchTrace(), stage=RolloutStage.OFF)
    with pytest.raises(GraphStageOffError):
        await uc.run(query="q", kb_id=None, collection_name=None, top_k=5,
                     max_hops=None, request_id="r")
