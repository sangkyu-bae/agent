from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.doc_browse.get_chunks_use_case import GetChunksUseCase


def _point(point_id: str, payload: dict) -> SimpleNamespace:
    return SimpleNamespace(id=point_id, payload=payload)


def _make_use_case(points: list) -> GetChunksUseCase:
    client = AsyncMock()
    client.scroll = AsyncMock(return_value=(points, None))
    logger = MagicMock()
    return GetChunksUseCase(qdrant_client=client, logger=logger)


def _base_payload(**overrides) -> dict:
    base = {
        "document_id": "doc-1",
        "filename": "a.pdf",
        "category": "policy",
        "user_id": "u1",
        "chunk_id": "c1",
        "chunk_index": 0,
        "chunk_type": "child",
        "content": "text",
        "total_chunks": 1,
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_returns_children_only_by_default():
    points = [
        _point("p1", _base_payload(chunk_id="c1", chunk_type="parent", chunk_index=0, content="parent text")),
        _point("p2", _base_payload(chunk_id="c2", chunk_type="child", chunk_index=0, content="child 0", parent_id="c1")),
        _point("p3", _base_payload(chunk_id="c3", chunk_type="child", chunk_index=1, content="child 1", parent_id="c1")),
    ]
    uc = _make_use_case(points)
    result = await uc.execute("col", "doc-1", include_parent=False)
    assert len(result.chunks) == 2
    assert all(c.chunk_type == "child" for c in result.chunks)
    assert result.parents is None


@pytest.mark.asyncio
async def test_sorts_by_chunk_index():
    points = [
        _point("p1", _base_payload(chunk_id="c3", chunk_type="child", chunk_index=2, content="third", parent_id="x")),
        _point("p2", _base_payload(chunk_id="c1", chunk_type="child", chunk_index=0, content="first", parent_id="x")),
        _point("p3", _base_payload(chunk_id="c2", chunk_type="child", chunk_index=1, content="second", parent_id="x")),
    ]
    uc = _make_use_case(points)
    result = await uc.execute("col", "doc-1", include_parent=False)
    indices = [c.chunk_index for c in result.chunks]
    assert indices == [0, 1, 2]


@pytest.mark.asyncio
async def test_returns_parent_child_hierarchy():
    points = [
        _point("p1", _base_payload(chunk_id="par1", chunk_type="parent", chunk_index=0, content="parent")),
        _point("p2", _base_payload(chunk_id="ch1", chunk_type="child", chunk_index=0, content="child 0", parent_id="par1")),
        _point("p3", _base_payload(chunk_id="ch2", chunk_type="child", chunk_index=1, content="child 1", parent_id="par1")),
    ]
    uc = _make_use_case(points)
    result = await uc.execute("col", "doc-1", include_parent=True)
    assert result.parents is not None
    assert len(result.parents) == 1
    assert result.parents[0].chunk_id == "par1"
    assert len(result.parents[0].children) == 2


@pytest.mark.asyncio
async def test_maps_children_to_correct_parent():
    points = [
        _point("p1", _base_payload(chunk_id="par1", chunk_type="parent", chunk_index=0, content="parent 1")),
        _point("p2", _base_payload(chunk_id="par2", chunk_type="parent", chunk_index=1, content="parent 2")),
        _point("p3", _base_payload(chunk_id="ch1", chunk_type="child", chunk_index=0, content="child of par1", parent_id="par1")),
        _point("p4", _base_payload(chunk_id="ch2", chunk_type="child", chunk_index=0, content="child of par2", parent_id="par2")),
        _point("p5", _base_payload(chunk_id="ch3", chunk_type="child", chunk_index=1, content="child of par2", parent_id="par2")),
    ]
    uc = _make_use_case(points)
    result = await uc.execute("col", "doc-1", include_parent=True)
    assert len(result.parents) == 2
    par1 = next(p for p in result.parents if p.chunk_id == "par1")
    par2 = next(p for p in result.parents if p.chunk_id == "par2")
    assert len(par1.children) == 1
    assert len(par2.children) == 2


@pytest.mark.asyncio
async def test_handles_full_token_strategy():
    points = [
        _point("p1", _base_payload(chunk_id="c1", chunk_type="full", chunk_index=0, content="seg 0")),
        _point("p2", _base_payload(chunk_id="c2", chunk_type="full", chunk_index=1, content="seg 1")),
    ]
    uc = _make_use_case(points)
    result = await uc.execute("col", "doc-1", include_parent=False)
    assert result.chunk_strategy == "full_token"
    assert len(result.chunks) == 2
    assert result.parents is None


@pytest.mark.asyncio
async def test_handles_semantic_strategy():
    points = [
        _point("p1", _base_payload(chunk_id="c1", chunk_type="semantic", chunk_index=0, content="sem 0")),
        _point("p2", _base_payload(chunk_id="c2", chunk_type="semantic", chunk_index=1, content="sem 1")),
    ]
    uc = _make_use_case(points)
    result = await uc.execute("col", "doc-1", include_parent=False)
    assert result.chunk_strategy == "semantic"
    assert len(result.chunks) == 2


@pytest.mark.asyncio
async def test_ignores_include_parent_for_non_parent_child():
    points = [
        _point("p1", _base_payload(chunk_id="c1", chunk_type="full", chunk_index=0, content="text")),
    ]
    uc = _make_use_case(points)
    result = await uc.execute("col", "doc-1", include_parent=True)
    assert result.parents is None
    assert len(result.chunks) == 1


@pytest.mark.asyncio
async def test_detects_chunk_strategy():
    parent_child_points = [
        _point("p1", _base_payload(chunk_type="parent")),
        _point("p2", _base_payload(chunk_type="child")),
    ]
    uc = _make_use_case(parent_child_points)
    result = await uc.execute("col", "doc-1", include_parent=False)
    assert result.chunk_strategy == "parent_child"


@pytest.mark.asyncio
async def test_excludes_internal_metadata_keys():
    points = [
        _point("p1", _base_payload(
            chunk_id="c1",
            chunk_type="full",
            chunk_index=0,
            content="text",
            total_chunks=5,
            category="finance",
            custom_key="custom_val",
        )),
    ]
    uc = _make_use_case(points)
    result = await uc.execute("col", "doc-1", include_parent=False)
    meta = result.chunks[0].metadata
    for excluded in ("content", "chunk_id", "chunk_index", "chunk_type", "total_chunks"):
        assert excluded not in meta
    assert meta["category"] == "finance"
    assert meta["custom_key"] == "custom_val"


@pytest.mark.asyncio
async def test_returns_empty_for_nonexistent_document():
    uc = _make_use_case([])
    result = await uc.execute("col", "no-such-doc", include_parent=False)
    assert result.chunks == []
    assert result.total_chunks == 0
