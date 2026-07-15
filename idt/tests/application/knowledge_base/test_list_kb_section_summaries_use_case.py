"""ListKbSectionSummariesUseCase 단위 테스트 — kb-content-browser Design §4.2.

소스별 조회 + chunk_index 정렬(str→int, 실패 0) + 빈 목록.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.knowledge_base.content_browse_guard import KbDocumentContext
from src.application.knowledge_base.list_kb_section_summaries_use_case import (
    ListKbSectionSummariesUseCase,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.elasticsearch.schemas import ESSearchResult


def _user() -> User:
    return User(
        email="t@t.com",
        password_hash="h",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=1,
    )


def _ctx() -> KbDocumentContext:
    return KbDocumentContext(
        kb_id="kb-1",
        document_id="doc-1",
        collection_name="shared-col",
        filename="a.pdf",
        chunk_strategy="parent_child",
    )


def _point(point_id: str, payload: dict):
    return SimpleNamespace(id=point_id, payload=payload)


def _qdrant_section(idx, title="제1장", ref="sec-ref-1", chunk_id=None) -> dict:
    return {
        "content": f"섹션 요약 {idx}",
        "summary": f"섹션 요약 {idx}",
        "chunk_type": "section_summary",
        "chunk_id": chunk_id or f"ss-{idx}",
        "section_ref": ref,
        "clause_title": title,
        "chunk_index": str(idx),
        "keywords": ["규정"],
        "document_id": "doc-1",
        "kb_id": "kb-1",
    }


def _es_section(idx, title="제1장", ref="sec-ref-1") -> dict:
    return {
        "chunk_id": f"ss-{idx}",
        "chunk_type": "section_summary",
        "section_ref": ref,
        "clause_title": title,
        "summary_text": f"섹션 요약 {idx}",
        "summary_keywords": ["규정"],
        "document_id": "doc-1",
        "kb_id": "kb-1",
    }


def _make_use_case(qdrant_points=None, es_hits=None):
    guard = AsyncMock()
    guard.ensure.return_value = _ctx()
    client = AsyncMock()
    client.scroll = AsyncMock(return_value=(qdrant_points or [], None))
    es_repo = AsyncMock()
    es_repo.search = AsyncMock(return_value=es_hits or [])
    uc = ListKbSectionSummariesUseCase(
        guard=guard,
        qdrant_client=client,
        es_repo=es_repo,
        es_index="documents",
        logger=MagicMock(),
    )
    return uc, client, es_repo


class TestQdrantSource:
    @pytest.mark.asyncio
    async def test_returns_items_sorted_by_chunk_index(self):
        points = [
            _point("p2", _qdrant_section(2)),
            _point("p0", _qdrant_section(0)),
            _point("p1", _qdrant_section(1)),
        ]
        uc, _, _ = _make_use_case(qdrant_points=points)
        result = await uc.execute("kb-1", "doc-1", "qdrant", _user(), "req-1")
        assert result.source == "qdrant"
        assert result.total == 3
        assert [i.chunk_index for i in result.items] == [0, 1, 2]
        assert result.items[0].summary_text == "섹션 요약 0"
        assert result.items[0].clause_title == "제1장"
        assert result.items[0].keywords == ["규정"]

    @pytest.mark.asyncio
    async def test_scroll_filters_section_summary_type(self):
        uc, client, _ = _make_use_case()
        await uc.execute("kb-1", "doc-1", "qdrant", _user(), "req-2")
        kwargs = client.scroll.await_args.kwargs
        assert kwargs["collection_name"] == "shared-col"
        keys = {c.key for c in kwargs["scroll_filter"].must}
        assert keys == {"document_id", "chunk_type"}


class TestEsSource:
    @pytest.mark.asyncio
    async def test_returns_items_from_es(self):
        hits = [
            ESSearchResult(id="ss-0", score=1.0, source=_es_section(0), index="documents"),
            ESSearchResult(id="ss-1", score=1.0, source=_es_section(1), index="documents"),
        ]
        uc, client, _ = _make_use_case(es_hits=hits)
        result = await uc.execute("kb-1", "doc-1", "es", _user(), "req-3")
        assert result.source == "es"
        assert result.total == 2
        assert result.items[0].summary_text == "섹션 요약 0"
        client.scroll.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_es_missing_chunk_index_defaults_zero(self):
        """ES 섹션 요약 body에는 chunk_index가 없음 — 0 기본값 (Design D5)."""
        hits = [ESSearchResult(id="ss-0", score=1.0, source=_es_section(0), index="documents")]
        uc, _, _ = _make_use_case(es_hits=hits)
        result = await uc.execute("kb-1", "doc-1", "es", _user(), "req-4")
        assert result.items[0].chunk_index == 0

    @pytest.mark.asyncio
    async def test_es_query_filters(self):
        uc, _, es_repo = _make_use_case()
        await uc.execute("kb-1", "doc-1", "es", _user(), "req-5")
        query = es_repo.search.await_args.args[0]
        filters = query.query["bool"]["filter"]
        assert {"term": {"chunk_type": "section_summary"}} in filters
        assert {"term": {"kb_id": "kb-1"}} in filters


class TestEmpty:
    @pytest.mark.asyncio
    async def test_empty_list(self):
        uc, _, _ = _make_use_case()
        result = await uc.execute("kb-1", "doc-1", "qdrant", _user(), "req-6")
        assert result.items == []
        assert result.total == 0
