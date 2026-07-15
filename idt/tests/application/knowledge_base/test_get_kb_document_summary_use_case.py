"""GetKbDocumentSummaryUseCase 단위 테스트 — kb-content-browser Design §4.2.

D2: source=qdrant|es 분기, D5: summary_text 정규화, D6: 미생성 시 exists=False.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.knowledge_base.content_browse_guard import KbDocumentContext
from src.application.knowledge_base.get_kb_document_summary_use_case import (
    GetKbDocumentSummaryUseCase,
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
    from types import SimpleNamespace

    return SimpleNamespace(id=point_id, payload=payload)


def _qdrant_summary_payload() -> dict:
    return {
        "content": "문서 전체 요약",
        "summary": "문서 전체 요약",
        "chunk_type": "document_summary",
        "chunk_id": "ds-1",
        "document_id": "doc-1",
        "collection_name": "shared-col",
        "kb_id": "kb-1",
        "user_id": "1",
        "keywords": ["여신", "심사"],
        "section_count": "3",
    }


def _es_summary_source() -> dict:
    return {
        "chunk_id": "ds-1",
        "chunk_type": "document_summary",
        "summary_text": "문서 전체 요약",
        "summary_keywords": ["여신", "심사"],
        "document_id": "doc-1",
        "user_id": "1",
        "collection_name": "shared-col",
        "kb_id": "kb-1",
    }


def _make_use_case(qdrant_points=None, es_hits=None):
    guard = AsyncMock()
    guard.ensure.return_value = _ctx()
    client = AsyncMock()
    client.scroll = AsyncMock(return_value=(qdrant_points or [], None))
    es_repo = AsyncMock()
    es_repo.search = AsyncMock(return_value=es_hits or [])
    uc = GetKbDocumentSummaryUseCase(
        guard=guard,
        qdrant_client=client,
        es_repo=es_repo,
        es_index="documents",
        logger=MagicMock(),
    )
    return uc, guard, client, es_repo


class TestQdrantSource:
    @pytest.mark.asyncio
    async def test_returns_summary_from_qdrant(self):
        uc, _, client, es_repo = _make_use_case(
            qdrant_points=[_point("p1", _qdrant_summary_payload())]
        )
        result = await uc.execute("kb-1", "doc-1", "qdrant", _user(), "req-1")
        assert result.exists is True
        assert result.source == "qdrant"
        assert result.summary_text == "문서 전체 요약"
        assert result.keywords == ["여신", "심사"]
        assert result.section_count == 3
        assert result.chunk_id == "ds-1"
        es_repo.search.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_scroll_filters_document_and_chunk_type(self):
        uc, _, client, _ = _make_use_case(
            qdrant_points=[_point("p1", _qdrant_summary_payload())]
        )
        await uc.execute("kb-1", "doc-1", "qdrant", _user(), "req-2")
        kwargs = client.scroll.await_args.kwargs
        assert kwargs["collection_name"] == "shared-col"
        conditions = kwargs["scroll_filter"].must
        keys = {c.key for c in conditions}
        assert keys == {"document_id", "chunk_type"}

    @pytest.mark.asyncio
    async def test_missing_summary_returns_exists_false(self):
        uc, _, _, _ = _make_use_case(qdrant_points=[])
        result = await uc.execute("kb-1", "doc-1", "qdrant", _user(), "req-3")
        assert result.exists is False
        assert result.source == "qdrant"
        assert result.summary_text is None
        assert result.filename == "a.pdf"

    @pytest.mark.asyncio
    async def test_metadata_excludes_body_fields(self):
        uc, _, _, _ = _make_use_case(
            qdrant_points=[_point("p1", _qdrant_summary_payload())]
        )
        result = await uc.execute("kb-1", "doc-1", "qdrant", _user(), "req-4")
        assert "content" not in result.metadata
        assert "summary" not in result.metadata
        assert result.metadata["kb_id"] == "kb-1"
        assert result.metadata["chunk_type"] == "document_summary"


class TestEsSource:
    @pytest.mark.asyncio
    async def test_returns_summary_from_es(self):
        hits = [ESSearchResult(id="ds-1", score=1.0, source=_es_summary_source(), index="documents")]
        uc, _, client, _ = _make_use_case(es_hits=hits)
        result = await uc.execute("kb-1", "doc-1", "es", _user(), "req-5")
        assert result.exists is True
        assert result.source == "es"
        assert result.summary_text == "문서 전체 요약"
        assert result.keywords == ["여신", "심사"]
        client.scroll.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_es_query_filters(self):
        uc, _, _, es_repo = _make_use_case()
        await uc.execute("kb-1", "doc-1", "es", _user(), "req-6")
        query = es_repo.search.await_args.args[0]
        assert query.index == "documents"
        filters = query.query["bool"]["filter"]
        assert {"term": {"kb_id": "kb-1"}} in filters
        assert {"term": {"document_id": "doc-1"}} in filters
        assert {"term": {"chunk_type": "document_summary"}} in filters

    @pytest.mark.asyncio
    async def test_es_missing_returns_exists_false(self):
        uc, _, _, _ = _make_use_case(es_hits=[])
        result = await uc.execute("kb-1", "doc-1", "es", _user(), "req-7")
        assert result.exists is False
        assert result.source == "es"


class TestGuard:
    @pytest.mark.asyncio
    async def test_guard_error_propagates(self):
        uc, guard, client, es_repo = _make_use_case()
        guard.ensure.side_effect = ValueError("Document 'doc-1' not found in knowledge base 'kb-1'")
        with pytest.raises(ValueError, match="not found"):
            await uc.execute("kb-1", "doc-1", "qdrant", _user(), "req-8")
        client.scroll.assert_not_awaited()
        es_repo.search.assert_not_awaited()
