"""QdrantSectionSource 테스트 — parent scroll·정렬·done_refs (Design D1/D6)."""
from types import SimpleNamespace

import pytest

from src.infrastructure.section_summary.qdrant_section_source import (
    QdrantSectionSource,
)


class _FakeLogger:
    def debug(self, *a, **k): ...
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...
    def critical(self, *a, **k): ...


def _point(point_id: str, payload: dict) -> SimpleNamespace:
    return SimpleNamespace(id=point_id, payload=payload)


class _FakeClient:
    def __init__(self, points):
        self._points = points
        self.captured_filters = []

    async def scroll(self, collection_name, scroll_filter, limit, with_vectors):
        self.captured_filters.append(scroll_filter)
        return self._points, None


@pytest.mark.asyncio
async def test_list_sections_maps_and_sorts_by_chunk_index():
    points = [
        _point("q2", {
            "chunk_id": "p2", "clause_title": "제2조", "content": "본문2",
            "chunk_index": "1", "user_id": "7", "kb_id": "kb-1",
            "kb_name": "규정", "filename": "a.pdf", "chunk_type": "parent",
        }),
        _point("q1", {
            "chunk_id": "p1", "clause_title": "제1조", "content": "본문1",
            "chunk_index": "0", "chunk_type": "parent",
        }),
    ]
    client = _FakeClient(points)
    source = QdrantSectionSource(client, _FakeLogger())

    cards = await source.list_sections("col", "doc-1", "req-1")

    assert [c.section_ref for c in cards] == ["p1", "p2"]
    assert cards[1].title == "제2조"
    assert cards[1].meta["user_id"] == "7"
    assert cards[1].meta["filename"] == "a.pdf"
    # 필터에 document_id + chunk_type=parent 복합 조건
    conditions = client.captured_filters[0].must
    keys = {c.key: c.match.value for c in conditions}
    assert keys == {"document_id": "doc-1", "chunk_type": "parent"}


@pytest.mark.asyncio
async def test_empty_content_sections_are_skipped():
    points = [
        _point("q1", {"chunk_id": "p1", "content": "  ", "chunk_index": "0"}),
        _point("q2", {"chunk_id": "p2", "content": "본문", "chunk_index": "1"}),
    ]
    source = QdrantSectionSource(_FakeClient(points), _FakeLogger())
    cards = await source.list_sections("col", "doc-1", "req-1")
    assert [c.section_ref for c in cards] == ["p2"]


@pytest.mark.asyncio
async def test_list_summary_items_maps_sorts_and_skips_empty():
    """문서 요약 입력 수집 — 정렬·keywords 복원·빈 요약 스킵 (D6)."""
    points = [
        _point("s2", {
            "chunk_type": "section_summary", "clause_title": "제2조",
            "summary": "둘째 요약", "keywords": ["한도"], "chunk_index": "1",
            "kb_name": "규정", "user_id": "7", "filename": "a.pdf",
        }),
        _point("s1", {
            "chunk_type": "section_summary", "clause_title": "제1조",
            "summary": "첫째 요약", "keywords": ["대출", "금리"],
            "chunk_index": "0",
        }),
        _point("s3", {
            "chunk_type": "section_summary", "clause_title": "제3조",
            "summary": "  ", "keywords": ["무시"], "chunk_index": "2",
        }),
    ]
    client = _FakeClient(points)
    source = QdrantSectionSource(client, _FakeLogger())

    items = await source.list_summary_items("col", "doc-1", "req-1")

    assert [i.title for i in items] == ["제1조", "제2조"]
    assert items[0].keywords == ["대출", "금리"]
    assert items[1].meta["filename"] == "a.pdf"
    keys = {c.key: c.match.value for c in client.captured_filters[0].must}
    assert keys["chunk_type"] == "section_summary"


@pytest.mark.asyncio
async def test_list_done_refs_collects_section_refs():
    points = [
        _point("s1", {"section_ref": "p1", "chunk_type": "section_summary"}),
        _point("s2", {"section_ref": "p2", "chunk_type": "section_summary"}),
        _point("s3", {"chunk_type": "section_summary"}),  # ref 없음 → 무시
    ]
    client = _FakeClient(points)
    source = QdrantSectionSource(client, _FakeLogger())

    refs = await source.list_done_refs("col", "doc-1", "req-1")

    assert refs == {"p1", "p2"}
    keys = {c.key: c.match.value for c in client.captured_filters[0].must}
    assert keys["chunk_type"] == "section_summary"
