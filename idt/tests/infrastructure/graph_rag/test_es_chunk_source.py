"""EsChunkSource — 문서 청크를 ES 에서 읽어 추출 단위로 (Design §11.4 V1)."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.domain.elasticsearch.schemas import ESSearchResult
from src.infrastructure.graph_rag.es_chunk_reader import EsChunkSource


def _hit(cid, ctype, idx, content="본문"):
    return ESSearchResult(id=cid, score=1.0, index="docs", source={
        "chunk_id": cid, "chunk_type": ctype, "chunk_index": idx, "content": content,
        "document_id": "doc-1", "kb_id": "kb-1", "collection_name": "col",
    })


@pytest.mark.asyncio
async def test_reads_document_chunks_and_selects_parents():
    repo = MagicMock()
    repo.search = AsyncMock(return_value=[
        _hit("c1", "child", 1), _hit("p2", "parent", 2), _hit("p1", "parent", 0),
        _hit("s", "section_summary", 3),
    ])
    units = await EsChunkSource(repo, "docs", MagicMock()).list_units("doc-1", "r")
    assert [u.chunk_id for u in units] == ["p1", "p2"]
    assert units[0].kb_id == "kb-1" and units[0].collection_name == "col"
    query = repo.search.call_args.args[0]
    assert query.index == "docs"
    assert query.query == {"bool": {"filter": [{"term": {"document_id": "doc-1"}}]}}
    assert query.size >= 1000
