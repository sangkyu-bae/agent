"""RoutedRetrievalUseCase 오케스트레이터 테스트 (Design D2/D8, FR-07/FR-08)."""
from types import SimpleNamespace

import pytest

from src.application.routed_retrieval.use_case import RoutedRetrievalUseCase
from src.domain.hybrid_search.schemas import (
    HybridSearchResponse,
    HybridSearchResult,
)
from src.domain.routed_retrieval.policy import RoutedRetrievalPolicy
from src.domain.routed_retrieval.schemas import (
    DocumentCandidate,
    RoutedChunk,
    RoutedParams,
    RoutedScope,
    SectionCandidate,
)


class _FakeLogger:
    def debug(self, *a, **k): ...
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...
    def critical(self, *a, **k): ...


class _FakeEmbedding:
    def __init__(self):
        self.calls = 0

    async def embed_text(self, text):
        self.calls += 1
        return [0.1, 0.2]


class _FakeDocumentRouter:
    def __init__(self, docs):
        self._docs = docs
        self.calls = []

    async def route(self, query_vector, scope, top_k, request_id):
        self.calls.append((query_vector, scope, top_k))
        return self._docs


class _FakeSectionRouter:
    def __init__(self, sections):
        self._sections = sections
        self.calls = []

    async def route(self, query, query_vector, document_ids, scope, params, request_id):
        self.calls.append(document_ids)
        return self._sections


class _FakeExpander:
    def __init__(self, chunks):
        self._chunks = chunks
        self.calls = []

    async def expand(self, sections, documents_by_id, scope, request_id):
        self.calls.append((sections, documents_by_id))
        return self._chunks


class _FakeHybrid:
    def __init__(self, results=None, error=None):
        self._results = results or []
        self._error = error
        self.requests = []

    async def execute(self, request, request_id):
        if self._error is not None:
            raise self._error
        self.requests.append(request)
        return HybridSearchResponse(
            query=request.query, results=self._results,
            total_found=len(self._results), request_id=request_id,
        )


def _doc(document_id="doc-1"):
    return DocumentCandidate(document_id=document_id, score=0.9)


def _section(ref="p1"):
    return SectionCandidate(section_ref=ref, document_id="doc-1", score=0.03)


def _chunk(ref="p1"):
    return RoutedChunk(
        section_ref=ref, document_id="doc-1", content=f"본문 {ref}", score=0.03
    )


def _fb_hit(chunk_id="c1"):
    return HybridSearchResult(
        id=chunk_id, content="fb", score=0.01,
        bm25_rank=1, bm25_score=1.0, vector_rank=None, vector_score=None,
        source="bm25_only", metadata={"chunk_id": chunk_id},
    )


def _use_case(docs, sections, chunks, hybrid=None):
    embedding = _FakeEmbedding()
    doc_router = _FakeDocumentRouter(docs)
    section_router = _FakeSectionRouter(sections)
    expander = _FakeExpander(chunks)
    uc = RoutedRetrievalUseCase(
        embedding=embedding,
        document_router=doc_router,
        section_router=section_router,
        chunk_expander=expander,
        policy=RoutedRetrievalPolicy(),
        hybrid_search_getter=(lambda: hybrid) if hybrid else None,
        logger=_FakeLogger(),
    )
    return uc, SimpleNamespace(
        embedding=embedding, doc_router=doc_router,
        section_router=section_router, expander=expander, hybrid=hybrid,
    )


@pytest.mark.asyncio
async def test_full_descent_without_fallback():
    chunks = [_chunk(f"p{i}") for i in range(5)]
    hybrid = _FakeHybrid()
    uc, f = _use_case([_doc()], [_section()], chunks, hybrid)

    result = await uc.execute(
        "질의", RoutedScope(collection_name="col"), RoutedParams(top_k=5), "req-1"
    )

    assert f.embedding.calls == 1  # 임베딩 1회 (FR-07)
    assert f.section_router.calls == [["doc-1"]]
    assert len(result.results) == 5
    assert result.fallback_used is False
    assert result.document_candidates == 1
    assert result.section_candidates == 1
    assert hybrid.requests == []  # 충족 시 폴백 미호출


@pytest.mark.asyncio
async def test_no_documents_falls_back_entirely():
    hybrid = _FakeHybrid(results=[_fb_hit("c1"), _fb_hit("c2")])
    uc, f = _use_case([], [], [], hybrid)

    result = await uc.execute(
        "질의", RoutedScope(kb_id="kb-1"), RoutedParams(top_k=5), "req-1"
    )

    assert f.section_router.calls == []  # 문서 0건 → 하강 중단
    assert result.fallback_used is True
    assert result.fallback_count == 2
    assert all(c.from_fallback for c in result.results)
    assert hybrid.requests[0].metadata_filter == {"kb_id": "kb-1"}


@pytest.mark.asyncio
async def test_short_results_supplemented_with_dedup():
    hybrid = _FakeHybrid(results=[_fb_hit("p1"), _fb_hit("c9")])
    uc, _ = _use_case([_doc()], [_section()], [_chunk("p1")], hybrid)

    result = await uc.execute("질의", RoutedScope(), RoutedParams(top_k=3), "req-1")

    refs = [c.section_ref for c in result.results]
    assert refs == ["p1", "c9"]  # p1 중복 제외
    assert result.fallback_count == 1


@pytest.mark.asyncio
async def test_fallback_failure_keeps_routed_results():
    hybrid = _FakeHybrid(error=RuntimeError("hybrid down"))
    uc, _ = _use_case([_doc()], [_section()], [_chunk("p1")], hybrid)

    result = await uc.execute("질의", RoutedScope(), RoutedParams(top_k=5), "req-1")

    assert [c.section_ref for c in result.results] == ["p1"]
    assert result.fallback_used is False


@pytest.mark.asyncio
async def test_invalid_params_raise_value_error():
    uc, _ = _use_case([], [], [])
    with pytest.raises(ValueError):
        await uc.execute("질의", RoutedScope(), RoutedParams(top_k=0), "req-1")


@pytest.mark.asyncio
async def test_results_trimmed_to_top_k():
    chunks = [_chunk(f"p{i}") for i in range(8)]
    uc, _ = _use_case([_doc()], [_section()], chunks)

    result = await uc.execute("질의", RoutedScope(), RoutedParams(top_k=3), "req-1")

    assert len(result.results) == 3
