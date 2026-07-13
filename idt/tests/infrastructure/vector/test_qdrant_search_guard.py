"""QdrantVectorStore 요약 청크 격리 가드 테스트 (card-section-summary D8,
document-summary-routing D12).

기본 벡터 검색에는 must_not[chunk_type ∈ 요약 타입 집합]이 추가되고,
호출자가 명시적으로 요약 타입을 요구하면 가드가 적용되지 않는다.
"""
from types import SimpleNamespace

import pytest

from src.domain.vector.value_objects import SearchFilter
from src.infrastructure.vector.qdrant_vectorstore import QdrantVectorStore


class _FakeQdrantClient:
    def __init__(self):
        self.captured_filter = None

    async def query_points(self, collection_name, query, limit, query_filter, with_vectors):
        self.captured_filter = query_filter
        return SimpleNamespace(points=[])


def _store(client) -> QdrantVectorStore:
    return QdrantVectorStore(
        client=client, embedding=None, collection_name="col"
    )


_SUMMARY_TYPES = {"section_summary", "document_summary"}


def _must_not_types(qfilter) -> set[str]:
    if qfilter is None or not qfilter.must_not:
        return set()
    types: set[str] = set()
    for cond in qfilter.must_not:
        if getattr(cond, "key", None) != "chunk_type":
            continue
        match = cond.match
        if getattr(match, "any", None):
            types.update(match.any)
        elif hasattr(match, "value"):
            types.add(match.value)
    return types


@pytest.mark.asyncio
async def test_no_filter_gets_summary_guard():
    client = _FakeQdrantClient()
    await _store(client).search_by_vector(vector=[0.1], top_k=5)
    assert _must_not_types(client.captured_filter) == _SUMMARY_TYPES


@pytest.mark.asyncio
async def test_existing_filter_conditions_are_preserved():
    client = _FakeQdrantClient()
    sfilter = SearchFilter(metadata={"chunk_type": "child", "kb_id": "kb-1"})
    await _store(client).search_by_vector(vector=[0.1], top_k=5, filter=sfilter)

    qfilter = client.captured_filter
    must_keys = {c.key for c in (qfilter.must or [])}
    assert must_keys == {"chunk_type", "kb_id"}
    assert _must_not_types(qfilter) == _SUMMARY_TYPES


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "summary_type", ["section_summary", "document_summary"]
)
async def test_explicit_summary_filter_bypasses_guard(summary_type):
    """후속 라우팅 검색이 명시 필터로 각 요약 계층을 조회 (D12 bypass)."""
    client = _FakeQdrantClient()
    sfilter = SearchFilter(metadata={"chunk_type": summary_type})
    await _store(client).search_by_vector(vector=[0.1], top_k=5, filter=sfilter)

    qfilter = client.captured_filter
    assert _must_not_types(qfilter) == set()
    must_values = {c.match.value for c in (qfilter.must or [])}
    assert summary_type in must_values
