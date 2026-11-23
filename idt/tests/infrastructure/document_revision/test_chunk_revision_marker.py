"""QdrantEsChunkRevisionMarker — document-revision Design §1.2·§3.3.

Qdrant set_payload(filter=document_id) + ES update_by_query(term=document_id), 둘 다 멱등.
저장소별 실패는 결과 플래그로만 알리고 예외를 올리지 않는다(sync_state=pending 처리용).
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from qdrant_client import models

from src.domain.document_revision.value_objects import RevisionStatus
from src.infrastructure.document_revision.chunk_revision_marker import (
    QdrantEsChunkRevisionMarker,
)


def _marker(qdrant=None, es=None):
    q = qdrant or MagicMock()
    if qdrant is None:
        q.set_payload = AsyncMock()
    e = es or MagicMock()
    if es is None:
        e.update_by_query = AsyncMock(return_value=3)
        e.put_mapping = AsyncMock()
    return QdrantEsChunkRevisionMarker(q, e, "documents", MagicMock()), q, e


@pytest.mark.asyncio
async def test_marks_both_stores_by_document_id() -> None:
    marker, q, e = _marker()
    result = await marker.mark("col", "doc-1", RevisionStatus.SUPERSEDED, "r")

    assert result.ok
    kwargs = q.set_payload.call_args.kwargs
    assert kwargs["collection_name"] == "col"
    assert kwargs["payload"] == {"revision_status": "superseded"}
    selector = kwargs["points"]
    assert isinstance(selector, models.Filter)
    cond = selector.must[0]
    assert cond.key == "document_id" and cond.match.value == "doc-1"

    index, query, script, rid = e.update_by_query.call_args.args
    assert index == "documents"
    assert query == {"term": {"document_id": "doc-1"}}
    assert script["params"] == {"status": "superseded"}
    assert "revision_status" in script["source"]


@pytest.mark.asyncio
async def test_reactivate_writes_active() -> None:
    marker, q, e = _marker()
    await marker.mark("col", "doc-1", RevisionStatus.ACTIVE, "r")
    assert q.set_payload.call_args.kwargs["payload"] == {"revision_status": "active"}
    assert e.update_by_query.call_args.args[2]["params"] == {"status": "active"}


@pytest.mark.asyncio
async def test_mapping_ensured_once_per_index() -> None:
    marker, _, e = _marker()
    await marker.mark("col", "d1", RevisionStatus.SUPERSEDED, "r")
    await marker.mark("col", "d2", RevisionStatus.SUPERSEDED, "r")
    e.put_mapping.assert_awaited_once_with(
        "documents", {"revision_status": {"type": "keyword"}}, "r"
    )


@pytest.mark.asyncio
async def test_mapping_failure_does_not_block_update() -> None:
    es = MagicMock()
    es.put_mapping = AsyncMock(side_effect=RuntimeError("conflict"))
    es.update_by_query = AsyncMock(return_value=1)
    marker, _, _ = _marker(es=es)
    result = await marker.mark("col", "d1", RevisionStatus.SUPERSEDED, "r")
    assert result.es_ok


@pytest.mark.asyncio
async def test_qdrant_failure_is_reported_not_raised() -> None:
    q = MagicMock()
    q.set_payload = AsyncMock(side_effect=RuntimeError("down"))
    marker, _, e = _marker(qdrant=q)
    result = await marker.mark("col", "d1", RevisionStatus.SUPERSEDED, "r")
    assert (result.qdrant_ok, result.es_ok, result.ok) == (False, True, False)
    e.update_by_query.assert_awaited()  # 한쪽 실패가 다른 쪽을 막지 않는다


@pytest.mark.asyncio
async def test_es_failure_is_reported_not_raised() -> None:
    es = MagicMock()
    es.put_mapping = AsyncMock()
    es.update_by_query = AsyncMock(side_effect=RuntimeError("down"))
    marker, _, _ = _marker(es=es)
    result = await marker.mark("col", "d1", RevisionStatus.SUPERSEDED, "r")
    assert (result.qdrant_ok, result.es_ok) == (True, False)
