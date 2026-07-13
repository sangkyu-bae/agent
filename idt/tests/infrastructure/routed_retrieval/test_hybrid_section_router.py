"""HybridSectionRouter 테스트 — 벡터+BM25 RRF (summary-routed-retrieval Design D4)."""
from types import SimpleNamespace

import pytest

from src.domain.hybrid_search.policies import RRFFusionPolicy
from src.domain.routed_retrieval.schemas import RoutedParams, RoutedScope
from src.infrastructure.routed_retrieval.hybrid_section_router import (
    HybridSectionRouter,
)


class _FakeLogger:
    def debug(self, *a, **k): ...
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...
    def critical(self, *a, **k): ...


def _summary_point(summary_id: str, section_ref: str, document_id: str, score: float):
    return SimpleNamespace(
        id=SimpleNamespace(value=summary_id),
        content="섹션 요약",
        metadata={
            "section_ref": section_ref,
            "document_id": document_id,
            "clause_title": f"제{section_ref[-1]}조",
            "keywords": "['대출']",
            "summary": "섹션 요약",
        },
        score=score,
    )


def _es_hit(summary_id: str, section_ref: str, document_id: str, score: float):
    return SimpleNamespace(
        id=summary_id,
        score=score,
        source={
            "summary_text": "섹션 요약",
            "summary_keywords": ["대출", "한도"],
            "section_ref": section_ref,
            "document_id": document_id,
            "clause_title": f"제{section_ref[-1]}조",
            "chunk_type": "section_summary",
        },
        index="documents",
    )


class _FakeVectorStore:
    def __init__(self, docs):
        self._docs = docs
        self.captured_filter = None

    async def search_by_vector(self, vector, top_k, filter, collection_name):
        self.captured_filter = filter
        return self._docs


class _FakeEsRepo:
    def __init__(self, hits, error=None):
        self._hits = hits
        self._error = error
        self.captured_query = None

    async def search(self, query, request_id):
        if self._error is not None:
            raise self._error
        self.captured_query = query
        return self._hits


def _router(vector_docs, es_hits, es_error=None):
    store = _FakeVectorStore(vector_docs)
    es_repo = _FakeEsRepo(es_hits, error=es_error)
    router = HybridSectionRouter(
        vector_store=store,
        es_repo=es_repo,
        es_index="documents",
        rrf_policy=RRFFusionPolicy(),
        logger=_FakeLogger(),
    )
    return router, store, es_repo


@pytest.mark.asyncio
async def test_rrf_merges_on_shared_summary_id():
    """요약 ID 3자 일치 → 벡터/BM25 hit가 동일 키로 병합(source=both) (D4)."""
    router, store, es_repo = _router(
        vector_docs=[_summary_point("s1", "p1", "doc-1", 0.9)],
        es_hits=[_es_hit("s1", "p1", "doc-1", 3.2), _es_hit("s2", "p2", "doc-1", 2.0)],
    )
    sections = await router.route(
        "대출 한도", [0.1], ["doc-1"], RoutedScope(), RoutedParams(), "req-1"
    )

    by_ref = {s.section_ref: s for s in sections}
    assert by_ref["p1"].source == "both"
    assert by_ref["p1"].vector_rank == 1 and by_ref["p1"].bm25_rank == 1
    assert by_ref["p2"].source == "bm25_only"
    assert by_ref["p1"].clause_title == "제1조"


@pytest.mark.asyncio
async def test_vector_filter_scopes_documents_with_match_any():
    router, store, _ = _router([_summary_point("s1", "p1", "doc-1", 0.9)], [])
    await router.route(
        "질의", [0.1], ["doc-1", "doc-2"], RoutedScope(), RoutedParams(), "req-1"
    )

    assert store.captured_filter.metadata == {"chunk_type": "section_summary"}
    assert store.captured_filter.metadata_any == {
        "document_id": ["doc-1", "doc-2"]
    }


@pytest.mark.asyncio
async def test_es_query_shape():
    router, _, es_repo = _router([], [_es_hit("s1", "p1", "doc-1", 1.0)])
    await router.route(
        "여신 한도", [0.1], ["doc-1"],
        RoutedScope(kb_id="kb-1"), RoutedParams(section_top_n=7), "req-1",
    )

    q = es_repo.captured_query
    assert q.size == 7
    bool_q = q.query["bool"]
    multi = bool_q["must"][0]["multi_match"]
    assert multi["query"] == "여신 한도"
    assert multi["fields"] == ["summary_text^1.5", "summary_keywords"]
    filters = bool_q["filter"]
    assert {"term": {"chunk_type": "section_summary"}} in filters
    assert {"terms": {"document_id": ["doc-1"]}} in filters
    assert {"term": {"kb_id": "kb-1"}} in filters


@pytest.mark.asyncio
async def test_es_failure_degrades_to_vector_only():
    router, *_ = _router(
        [_summary_point("s1", "p1", "doc-1", 0.9)], [],
        es_error=RuntimeError("es down"),
    )
    sections = await router.route(
        "질의", [0.1], ["doc-1"], RoutedScope(), RoutedParams(), "req-1"
    )
    assert [s.section_ref for s in sections] == ["p1"]
    assert sections[0].source == "vector_only"


@pytest.mark.asyncio
async def test_hits_without_section_ref_are_skipped():
    broken = SimpleNamespace(
        id=SimpleNamespace(value="s9"), content="", metadata={}, score=0.5
    )
    router, *_ = _router([broken], [])
    sections = await router.route(
        "질의", [0.1], ["doc-1"], RoutedScope(), RoutedParams(), "req-1"
    )
    assert sections == []
