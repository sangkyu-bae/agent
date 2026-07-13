"""QdrantDocumentRouter 테스트 (summary-routed-retrieval Design D3)."""
from types import SimpleNamespace

import pytest

from src.domain.routed_retrieval.schemas import RoutedScope
from src.infrastructure.routed_retrieval.qdrant_document_router import (
    QdrantDocumentRouter,
)


class _FakeLogger:
    def debug(self, *a, **k): ...
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...
    def critical(self, *a, **k): ...


class _FakeVectorStore:
    def __init__(self, docs):
        self._docs = docs
        self.captured = None

    async def search_by_vector(self, vector, top_k, filter, collection_name):
        self.captured = SimpleNamespace(
            vector=vector, top_k=top_k, filter=filter,
            collection_name=collection_name,
        )
        return self._docs


def _doc(document_id: str, score: float = 0.9) -> SimpleNamespace:
    return SimpleNamespace(
        id=SimpleNamespace(value=f"point-{document_id}"),
        content="문서 요약 5줄",
        metadata={
            "document_id": document_id,
            "summary": "문서 요약 5줄",
            "keywords": "['대출', '금리']",  # payload 문자열 캐스팅 산물
            "filename": "rule.pdf",
            "chunk_type": "document_summary",
        },
        score=score,
    )


@pytest.mark.asyncio
async def test_routes_with_document_summary_filter_and_kb_scope():
    store = _FakeVectorStore([_doc("doc-1")])
    router = QdrantDocumentRouter(store, _FakeLogger())

    candidates = await router.route(
        [0.1], RoutedScope(collection_name="col", kb_id="kb-1"), 5, "req-1"
    )

    assert store.captured.top_k == 5
    assert store.captured.collection_name == "col"
    assert store.captured.filter.metadata == {
        "chunk_type": "document_summary",
        "kb_id": "kb-1",
    }
    assert candidates[0].document_id == "doc-1"
    assert candidates[0].summary == "문서 요약 5줄"
    assert candidates[0].keywords == ["대출", "금리"]
    assert candidates[0].filename == "rule.pdf"


@pytest.mark.asyncio
async def test_no_kb_scope_omits_kb_filter():
    store = _FakeVectorStore([])
    router = QdrantDocumentRouter(store, _FakeLogger())

    await router.route([0.1], RoutedScope(), 3, "req-1")

    assert store.captured.filter.metadata == {"chunk_type": "document_summary"}


@pytest.mark.asyncio
async def test_hits_without_document_id_are_skipped():
    broken = SimpleNamespace(
        id=SimpleNamespace(value="p"), content="", metadata={}, score=0.5
    )
    store = _FakeVectorStore([broken, _doc("doc-2", 0.8)])
    router = QdrantDocumentRouter(store, _FakeLogger())

    candidates = await router.route([0.1], RoutedScope(), 5, "req-1")

    assert [c.document_id for c in candidates] == ["doc-2"]
