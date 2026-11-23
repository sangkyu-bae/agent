"""superseded 청크 기본 제외 가드 — document-revision Design §9.5 G1~G5 (Plan SC-1).

모든 지점은 must_not[revision_status == superseded] 를 붙인다. 필드가 없는 기존 청크는
걸리지 않으므로 기존 검색 결과는 변하지 않는다.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from qdrant_client import models
from src.application.hybrid_search.use_case import HybridSearchUseCase
from src.domain.document_revision.search_guard import es_revision_guard_clause
from src.domain.hybrid_search.policies import RRFFusionPolicy
from src.domain.hybrid_search.schemas import HybridSearchRequest
from src.domain.retriever.value_objects.metadata_filter import MetadataFilter
from src.domain.routed_retrieval.schemas import RoutedParams, RoutedScope
from src.domain.vector.value_objects import SearchFilter
from src.infrastructure.document_revision.qdrant_guard import (
    apply_revision_guard,
    revision_guard_condition,
)
from src.infrastructure.graph_rag.es_evidence_fetcher import EsEvidenceFetcher
from src.infrastructure.retriever.qdrant_retriever import QdrantRetriever
from src.infrastructure.routed_retrieval.hybrid_section_router import (
    HybridSectionRouter,
)
from src.infrastructure.vector.qdrant_vectorstore import QdrantVectorStore

GUARD = es_revision_guard_clause()


def _has_revision_guard(qfilter: models.Filter | None) -> bool:
    if qfilter is None or not qfilter.must_not:
        return False
    return any(
        getattr(c, "key", None) == "revision_status"
        and getattr(c.match, "value", None) == "superseded"
        for c in qfilter.must_not
    )


# ── qdrant_guard 헬퍼 ────────────────────────────────────────
class TestQdrantGuardHelper:
    def test_condition(self) -> None:
        cond = revision_guard_condition()
        assert cond.key == "revision_status"
        assert cond.match.value == "superseded"

    def test_none_filter_becomes_must_not_only(self) -> None:
        f = apply_revision_guard(None)
        assert _has_revision_guard(f)
        assert not f.must

    def test_existing_clauses_preserved(self) -> None:
        base = models.Filter(
            must=[models.FieldCondition(key="kb_id", match=models.MatchValue(value="k"))],
            should=[models.FieldCondition(key="a", match=models.MatchValue(value="b"))],
            must_not=[models.FieldCondition(key="chunk_type", match=models.MatchValue(value="x"))],
            min_should=None,
        )
        f = apply_revision_guard(base)
        assert f.must == base.must
        assert f.should == base.should
        assert len(f.must_not) == 2 and _has_revision_guard(f)

    def test_idempotent(self) -> None:
        f = apply_revision_guard(apply_revision_guard(None))
        assert len(f.must_not) == 1


# ── G1 QdrantVectorStore.search_by_vector ───────────────────
class _FakeQdrant:
    def __init__(self) -> None:
        self.kwargs: dict = {}

    async def query_points(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(points=[])


class TestG1VectorStore:
    @pytest.mark.asyncio
    async def test_no_filter(self) -> None:
        client = _FakeQdrant()
        await QdrantVectorStore(client, None, "col").search_by_vector([0.1], 5)
        assert _has_revision_guard(client.kwargs["query_filter"])

    @pytest.mark.asyncio
    async def test_with_filter(self) -> None:
        client = _FakeQdrant()
        await QdrantVectorStore(client, None, "col").search_by_vector(
            [0.1], 5, SearchFilter(metadata={"kb_id": "k"})
        )
        assert _has_revision_guard(client.kwargs["query_filter"])

    @pytest.mark.asyncio
    async def test_summary_request_still_guarded(self) -> None:
        # 요약 가드는 요약 타입 요청 시 해제되지만 개정 가드는 해제되지 않는다
        client = _FakeQdrant()
        await QdrantVectorStore(client, None, "col").search_by_vector(
            [0.1], 5, SearchFilter(metadata={"chunk_type": "section_summary"})
        )
        assert _has_revision_guard(client.kwargs["query_filter"])


# ── G2 QdrantRetriever ──────────────────────────────────────
class TestG2Retriever:
    def _retriever(self, client) -> QdrantRetriever:
        emb = MagicMock()
        emb.embed_text = AsyncMock(return_value=[0.1])
        return QdrantRetriever(client, "col", emb)

    @pytest.mark.asyncio
    async def test_no_filter(self) -> None:
        client = _FakeQdrant()
        await self._retriever(client).retrieve_with_scores("q")
        assert _has_revision_guard(client.kwargs["query_filter"])

    @pytest.mark.asyncio
    async def test_with_filter(self) -> None:
        client = _FakeQdrant()
        await self._retriever(client).retrieve_with_scores(
            "q", filters=MetadataFilter(document_id="d1")
        )
        f = client.kwargs["query_filter"]
        assert _has_revision_guard(f) and f.must

    @pytest.mark.asyncio
    async def test_metadata_only_scroll(self) -> None:
        client = MagicMock()
        client.scroll = AsyncMock(return_value=([], None))
        await self._retriever(client).retrieve_by_metadata(
            MetadataFilter(document_id="d1")
        )
        assert _has_revision_guard(client.scroll.call_args.kwargs["scroll_filter"])


# ── G3 HybridSearchUseCase BM25 ─────────────────────────────
def _hybrid():
    es = MagicMock()
    es.search = AsyncMock(return_value=[])
    vs = MagicMock()
    vs.search_by_vector = AsyncMock(return_value=[])
    emb = MagicMock()
    emb.embed_text = AsyncMock(return_value=[0.1])
    uc = HybridSearchUseCase(
        es_repo=es, embedding=emb, vector_store=vs, es_index="documents",
        logger=MagicMock(),
    )
    return uc, es


class TestG3HybridBm25:
    @pytest.mark.asyncio
    async def test_no_filter_wraps_bool_with_guard(self) -> None:
        uc, es = _hybrid()
        await uc.execute(HybridSearchRequest(query="대출"), "r")
        q = es.search.call_args[0][0].query
        assert GUARD in q["bool"]["filter"]
        assert "multi_match" in q["bool"]["must"][0]

    @pytest.mark.asyncio
    async def test_with_filters_appends_guard(self) -> None:
        uc, es = _hybrid()
        await uc.execute(
            HybridSearchRequest(query="대출", metadata_filter={"kb_id": "k"}), "r"
        )
        filters = es.search.call_args[0][0].query["bool"]["filter"]
        assert filters[0] == {"term": {"kb_id": "k"}}
        assert filters[-1] == GUARD


# ── G4 HybridSectionRouter BM25 ─────────────────────────────
class TestG4SectionRouter:
    @pytest.mark.asyncio
    async def test_bm25_query_has_guard(self) -> None:
        es = MagicMock()
        es.search = AsyncMock(return_value=[])
        vs = MagicMock()
        vs.search_by_vector = AsyncMock(return_value=[])
        router = HybridSectionRouter(vs, es, "documents", RRFFusionPolicy(), MagicMock())
        await router.route("q", [0.1], ["d1"], RoutedScope(), RoutedParams(), "r")
        filters = es.search.call_args[0][0].query["bool"]["filter"]
        assert filters[-1] == GUARD


# ── G5 EsEvidenceFetcher (Graph RAG) ────────────────────────
class TestG5EvidenceFetcher:
    @pytest.mark.asyncio
    async def test_guard_appended_last(self) -> None:
        es = MagicMock()
        es.search = AsyncMock(return_value=[])
        await EsEvidenceFetcher(es, "idx", MagicMock()).fetch(
            ["c1"], hard_filter={}, lenient_filter={}, collection_name=None,
            es_index=None, request_id="r",
        )
        filters = es.search.call_args.args[0].query["bool"]["filter"]
        assert filters[0] == {"ids": {"values": ["c1"]}}
        assert filters[-1] == GUARD
