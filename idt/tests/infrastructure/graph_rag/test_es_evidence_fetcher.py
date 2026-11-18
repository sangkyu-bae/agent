"""EsEvidenceFetcher — ids + 권한 필터 (FR-12)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.graph_rag.es_evidence_fetcher import EsEvidenceFetcher


@pytest.mark.asyncio
async def test_fetch_applies_ids_and_tool_filters():
    repo = MagicMock()
    repo.search = AsyncMock(return_value=[
        SimpleNamespace(id="c1", score=1.0,
                        source={"content": "본문", "document_id": "d", "chunk_index": 3}),
    ])
    hits = await EsEvidenceFetcher(repo, "default-idx", MagicMock()).fetch(
        ["c1", "c2"], hard_filter={"kb_id": "kb1"},
        lenient_filter={"department": "d1"}, collection_name="col",
        es_index=None, request_id="r",
    )
    q = repo.search.call_args.args[0]
    assert q.index == "default-idx" and q.size == 2
    filters = q.query["bool"]["filter"]
    assert filters[0] == {"ids": {"values": ["c1", "c2"]}}
    assert {"term": {"kb_id": "kb1"}} in filters
    assert {"term": {"collection_name": "col"}} in filters
    lenient = filters[2]["bool"]["should"]
    assert lenient[0] == {"term": {"department": "d1"}}
    assert hits[0].id == "c1" and hits[0].content == "본문" and hits[0].source == "graph"
    assert hits[0].metadata == {"document_id": "d", "chunk_index": "3"}


@pytest.mark.asyncio
async def test_empty_ids_skip_es():
    repo = MagicMock()
    repo.search = AsyncMock()
    assert await EsEvidenceFetcher(repo, "i", MagicMock()).fetch(
        [], hard_filter={}, lenient_filter={}, collection_name=None, es_index=None,
        request_id="r") == []
    repo.search.assert_not_called()
