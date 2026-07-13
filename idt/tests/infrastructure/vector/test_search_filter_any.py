"""SearchFilter.metadata_any → Qdrant MatchAny 변환 테스트 (Design D6).

기존 equality 경로·요약 가드가 확장 후에도 불변임을 함께 고정한다.
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
    return QdrantVectorStore(client=client, embedding=None, collection_name="col")


def _must_conditions(qfilter) -> dict:
    result = {}
    for cond in (qfilter.must or []):
        match = cond.match
        if getattr(match, "any", None):
            result[cond.key] = list(match.any)
        else:
            result[cond.key] = match.value
    return result


@pytest.mark.asyncio
async def test_metadata_any_builds_match_any_condition():
    client = _FakeQdrantClient()
    sfilter = SearchFilter(
        metadata={"chunk_type": "section_summary"},
        metadata_any={"document_id": ["doc-1", "doc-2"]},
    )
    await _store(client).search_by_vector(vector=[0.1], top_k=5, filter=sfilter)

    conditions = _must_conditions(client.captured_filter)
    assert conditions["chunk_type"] == "section_summary"
    assert conditions["document_id"] == ["doc-1", "doc-2"]


@pytest.mark.asyncio
async def test_empty_metadata_any_adds_no_condition():
    client = _FakeQdrantClient()
    sfilter = SearchFilter(metadata={"kb_id": "kb-1"}, metadata_any={"document_id": []})
    await _store(client).search_by_vector(vector=[0.1], top_k=5, filter=sfilter)

    conditions = _must_conditions(client.captured_filter)
    assert "document_id" not in conditions
    assert conditions["kb_id"] == "kb-1"


@pytest.mark.asyncio
async def test_summary_guard_unchanged_with_metadata_any():
    """metadata_any 사용 시에도 요약 가드 규칙(bypass 포함) 불변 (D6 회귀 가드)."""
    client = _FakeQdrantClient()
    # 요약 타입 명시 → 가드 해제
    sfilter = SearchFilter(
        metadata={"chunk_type": "section_summary"},
        metadata_any={"document_id": ["doc-1"]},
    )
    await _store(client).search_by_vector(vector=[0.1], top_k=5, filter=sfilter)
    assert not (client.captured_filter.must_not or [])

    # 일반 검색 → 가드 유지
    client2 = _FakeQdrantClient()
    sfilter2 = SearchFilter(metadata_any={"document_id": ["doc-1"]})
    await _store(client2).search_by_vector(vector=[0.1], top_k=5, filter=sfilter2)
    assert client2.captured_filter.must_not


def test_is_empty_accounts_for_metadata_any():
    assert SearchFilter().is_empty()
    assert not SearchFilter(metadata_any={"document_id": ["d1"]}).is_empty()
