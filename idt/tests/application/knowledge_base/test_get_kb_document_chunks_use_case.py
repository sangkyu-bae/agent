"""GetKbDocumentChunksUseCase 단위 테스트 — kb-content-browser Design §4.2 D3.

요약 chunk_type 제외, q 검색(qdrant=contains / es=match), include_parent 계층,
search_mode 값 검증.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.knowledge_base.content_browse_guard import KbDocumentContext
from src.application.knowledge_base.get_kb_document_chunks_use_case import (
    GetKbDocumentChunksUseCase,
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


def _ctx(strategy: str = "parent_child") -> KbDocumentContext:
    return KbDocumentContext(
        kb_id="kb-1",
        document_id="doc-1",
        collection_name="shared-col",
        filename="a.pdf",
        chunk_strategy=strategy,
    )


def _point(point_id: str, payload: dict):
    return SimpleNamespace(id=point_id, payload=payload)


def _chunk(chunk_id, chunk_type, idx, content, parent_id=None) -> dict:
    payload = {
        "chunk_id": chunk_id,
        "chunk_type": chunk_type,
        "chunk_index": str(idx),
        "content": content,
        "document_id": "doc-1",
        "kb_id": "kb-1",
        "filename": "a.pdf",
    }
    if parent_id:
        payload["parent_id"] = parent_id
    return payload


def _default_points():
    return [
        _point("p1", _chunk("par1", "parent", 0, "여신심사 일반기준 전체")),
        _point("p2", _chunk("ch1", "child", 0, "심사역은 상환능력을 본다", parent_id="par1")),
        _point("p3", _chunk("ch2", "child", 1, "담보평가는 감정평가로 한다", parent_id="par1")),
        _point("p4", _chunk("ss1", "section_summary", 0, "요약")),
        _point("p5", _chunk("ds1", "document_summary", 0, "문서 요약")),
    ]


def _make_use_case(qdrant_points=None, es_side_effect=None):
    guard = AsyncMock()
    guard.ensure.return_value = _ctx()
    client = AsyncMock()
    client.scroll = AsyncMock(return_value=(qdrant_points or [], None))
    es_repo = AsyncMock()
    if es_side_effect is not None:
        es_repo.search = AsyncMock(side_effect=es_side_effect)
    else:
        es_repo.search = AsyncMock(return_value=[])
    uc = GetKbDocumentChunksUseCase(
        guard=guard,
        qdrant_client=client,
        es_repo=es_repo,
        es_index="documents",
        logger=MagicMock(),
    )
    return uc, client, es_repo


class TestQdrantSource:
    @pytest.mark.asyncio
    async def test_excludes_summary_chunk_types(self):
        uc, _, _ = _make_use_case(qdrant_points=_default_points())
        result = await uc.execute("kb-1", "doc-1", "qdrant", False, None, _user(), "req-1")
        assert result.total_chunks == 3
        assert all(
            c.chunk_type not in ("section_summary", "document_summary")
            for c in result.chunks
        )
        assert result.search_mode is None

    @pytest.mark.asyncio
    async def test_include_parent_builds_hierarchy(self):
        uc, _, _ = _make_use_case(qdrant_points=_default_points())
        result = await uc.execute("kb-1", "doc-1", "qdrant", True, None, _user(), "req-2")
        assert result.parents is not None
        assert result.parents[0].chunk_id == "par1"
        assert len(result.parents[0].children) == 2

    @pytest.mark.asyncio
    async def test_q_contains_filter(self):
        """qdrant 소스 검색은 대소문자 무시 부분일치 (search_mode=contains)."""
        uc, _, es_repo = _make_use_case(qdrant_points=_default_points())
        result = await uc.execute("kb-1", "doc-1", "qdrant", False, "담보", _user(), "req-3")
        assert result.search_mode == "contains"
        assert result.total_chunks == 1
        assert result.chunks[0].chunk_id == "ch2"
        es_repo.search.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_q_hierarchy_keeps_matching_groups_only(self):
        points = _default_points() + [
            _point("p6", _chunk("par2", "parent", 1, "국내 경제 동향")),
            _point("p7", _chunk("ch3", "child", 0, "물가지수 분석", parent_id="par2")),
        ]
        uc, _, _ = _make_use_case(qdrant_points=points)
        result = await uc.execute("kb-1", "doc-1", "qdrant", True, "담보", _user(), "req-4")
        assert len(result.parents) == 1
        assert result.parents[0].chunk_id == "par1"
        assert [c.chunk_id for c in result.parents[0].children] == ["ch2"]

    @pytest.mark.asyncio
    async def test_q_parent_match_keeps_all_children(self):
        """parent 본문이 매칭되면 그룹 전체(children 포함) 유지 (Design §4.1)."""
        uc, _, _ = _make_use_case(qdrant_points=_default_points())
        result = await uc.execute("kb-1", "doc-1", "qdrant", True, "일반기준", _user(), "req-5")
        assert len(result.parents) == 1
        assert len(result.parents[0].children) == 2

    @pytest.mark.asyncio
    async def test_filename_from_context_when_payload_missing(self):
        points = [_point("p1", {k: v for k, v in _chunk("c1", "full", 0, "본문").items() if k != "filename"})]
        uc, _, _ = _make_use_case(qdrant_points=points)
        result = await uc.execute("kb-1", "doc-1", "qdrant", False, None, _user(), "req-6")
        assert result.filename == "a.pdf"


class TestEsSource:
    def _es_hits(self):
        return [
            ESSearchResult(id="par1", score=1.0, source=_chunk("par1", "parent", 0, "여신심사 일반기준 전체"), index="documents"),
            ESSearchResult(id="ch1", score=1.0, source=_chunk("ch1", "child", 0, "심사역은 상환능력을 본다", parent_id="par1"), index="documents"),
            ESSearchResult(id="ch2", score=1.0, source=_chunk("ch2", "child", 1, "담보평가는 감정평가로 한다", parent_id="par1"), index="documents"),
        ]

    @pytest.mark.asyncio
    async def test_returns_chunks_from_es(self):
        uc, client, _ = _make_use_case(es_side_effect=[self._es_hits()])
        result = await uc.execute("kb-1", "doc-1", "es", False, None, _user(), "req-7")
        assert result.source == "es"
        assert result.total_chunks == 3  # 전체 수 (GetChunksUseCase 의미론과 동일)
        assert len(result.chunks) == 2  # flat 목록은 parent 제외
        client.scroll.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_es_fetch_query_excludes_summaries(self):
        uc, _, es_repo = _make_use_case(es_side_effect=[self._es_hits()])
        await uc.execute("kb-1", "doc-1", "es", False, None, _user(), "req-8")
        query = es_repo.search.await_args_list[0].args[0]
        bool_q = query.query["bool"]
        assert {"term": {"kb_id": "kb-1"}} in bool_q["filter"]
        assert {"term": {"document_id": "doc-1"}} in bool_q["filter"]
        assert bool_q["must_not"] == [
            {"terms": {"chunk_type": ["section_summary", "document_summary"]}}
        ]

    @pytest.mark.asyncio
    async def test_q_uses_es_match_query(self):
        """es 소스 검색은 match 쿼리 (search_mode=match) — 2차 조회로 매칭 id 획득."""
        match_hits = [
            ESSearchResult(id="ch2", score=2.0, source={"chunk_id": "ch2"}, index="documents"),
        ]
        uc, _, es_repo = _make_use_case(es_side_effect=[self._es_hits(), match_hits])
        result = await uc.execute("kb-1", "doc-1", "es", False, "담보", _user(), "req-9")
        assert result.search_mode == "match"
        assert result.total_chunks == 1
        assert result.chunks[0].chunk_id == "ch2"
        match_query = es_repo.search.await_args_list[1].args[0]
        assert match_query.query["bool"]["must"] == [{"match": {"content": "담보"}}]


class TestGuard:
    @pytest.mark.asyncio
    async def test_guard_error_propagates(self):
        uc, client, _ = _make_use_case()
        uc._guard.ensure.side_effect = PermissionError("No read access")
        with pytest.raises(PermissionError):
            await uc.execute("kb-1", "doc-1", "qdrant", False, None, _user(), "req-10")
        client.scroll.assert_not_awaited()
