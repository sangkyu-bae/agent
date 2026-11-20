"""검색 결과 머리말 이음매 S3 — answer-citation-verification §9.2.

라벨러가 없거나 실패하면 기존 `[출처: 파일]` 문자열 그대로(FR-15).
"""

from unittest.mock import MagicMock

import pytest
from src.application.rag_agent.tools import InternalDocumentSearchTool
from src.domain.hybrid_search.schemas import HybridSearchResult
from src.domain.routed_retrieval.schemas import RoutedChunk


def _hit(i: int, page=None) -> HybridSearchResult:
    meta = {"source": f"doc{i}.pdf", "document_id": f"d{i}"}
    if page is not None:
        meta["page"] = page
    return HybridSearchResult(
        id=f"chunk-{i}",
        content=f"본문{i}",
        score=0.9,
        bm25_rank=1,
        bm25_score=1.0,
        vector_rank=1,
        vector_score=0.9,
        source="both",
        metadata=meta,
    )


def _tool(labeler=None) -> InternalDocumentSearchTool:
    return InternalDocumentSearchTool(
        hybrid_search_use_case=MagicMock(), citation_labeler=labeler
    )


class _Labeler:
    def __init__(self) -> None:
        self.calls = []

    def label(self, **kw):
        self.calls.append(kw)
        return f"[출처 {len(self.calls)}: {kw['source']}]"


@pytest.mark.asyncio
async def test_without_labeler_format_is_unchanged():
    text = await _tool()._format_results([_hit(1), _hit(2)])
    assert text == "[출처: doc1.pdf]\n본문1\n\n[출처: doc2.pdf]\n본문2"


@pytest.mark.asyncio
async def test_labeler_header_is_used_and_receives_chunk_info():
    labeler = _Labeler()
    text = await _tool(labeler)._format_results([_hit(1, page="3"), _hit(2)])
    assert text == "[출처 1: doc1.pdf]\n본문1\n\n[출처 2: doc2.pdf]\n본문2"
    assert labeler.calls[0] == {
        "source": "doc1.pdf",
        "chunk_id": "chunk-1",
        "document_id": "d1",
        "page": "3",
        "text": "본문1",
    }


@pytest.mark.asyncio
async def test_labeler_none_or_error_falls_back_to_plain_header():
    none_labeler = MagicMock()
    none_labeler.label.return_value = None
    assert (
        await _tool(none_labeler)._format_results([_hit(1)])
    ) == "[출처: doc1.pdf]\n본문1"
    broken = MagicMock()
    broken.label.side_effect = RuntimeError("boom")
    assert (await _tool(broken)._format_results([_hit(1)])) == "[출처: doc1.pdf]\n본문1"


@pytest.mark.asyncio
async def test_routed_results_use_labeler_too():
    labeler = _Labeler()
    chunk = RoutedChunk(
        section_ref="c9",
        document_id="doc-2",
        content="폴백 본문",
        score=0.01,
        clause_title="",
        from_fallback=True,
    )
    text = await _tool(labeler)._format_routed_results([chunk])
    assert text == "[출처 1: doc-2]\n폴백 본문"
    assert labeler.calls[0]["chunk_id"] == "c9"
