"""EsChunkExpander 테스트 — ES ids query 확장 (summary-routed-retrieval Design D5)."""
from types import SimpleNamespace

import pytest

from src.domain.routed_retrieval.schemas import (
    DocumentCandidate,
    RoutedScope,
    SectionCandidate,
)
from src.infrastructure.routed_retrieval.es_chunk_expander import (
    EsChunkExpander,
)


class _FakeLogger:
    def __init__(self):
        self.warnings = []

    def debug(self, *a, **k): ...
    def info(self, *a, **k): ...
    def warning(self, msg, **k):
        self.warnings.append(msg)
    def error(self, *a, **k): ...
    def critical(self, *a, **k): ...


class _FakeEsRepo:
    def __init__(self, hits):
        self._hits = hits
        self.captured_query = None

    async def search(self, query, request_id):
        self.captured_query = query
        return self._hits


def _section(ref: str, score: float = 0.02) -> SectionCandidate:
    return SectionCandidate(
        section_ref=ref, document_id="doc-1", score=score,
        summary="섹션 요약", clause_title=f"제{ref[-1]}조",
    )


def _parent_hit(ref: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=ref, score=1.0,
        source={
            "content": f"조 본문 {ref}",
            "chunk_id": ref,
            "chunk_type": "parent",
            "document_id": "doc-1",
        },
        index="documents",
    )


@pytest.mark.asyncio
async def test_expands_with_ids_query_preserving_section_order():
    es_repo = _FakeEsRepo([_parent_hit("p2"), _parent_hit("p1")])
    expander = EsChunkExpander(es_repo, "documents", _FakeLogger())
    docs = {"doc-1": DocumentCandidate(document_id="doc-1", score=0.9)}

    chunks = await expander.expand(
        [_section("p1", 0.03), _section("p2", 0.02)], docs, RoutedScope(), "req-1"
    )

    assert es_repo.captured_query.query == {"ids": {"values": ["p1", "p2"]}}
    assert es_repo.captured_query.size == 2
    assert [c.section_ref for c in chunks] == ["p1", "p2"]  # 섹션 순위 유지
    assert chunks[0].content == "조 본문 p1"
    assert chunks[0].document is docs["doc-1"]
    assert chunks[0].section.summary == "섹션 요약"
    assert chunks[0].clause_title == "제1조"


@pytest.mark.asyncio
async def test_missing_refs_are_skipped_with_warning():
    logger = _FakeLogger()
    expander = EsChunkExpander(_FakeEsRepo([_parent_hit("p1")]), "documents", logger)

    chunks = await expander.expand(
        [_section("p1"), _section("p9")], {}, RoutedScope(), "req-1"
    )

    assert [c.section_ref for c in chunks] == ["p1"]
    assert logger.warnings


@pytest.mark.asyncio
async def test_empty_sections_short_circuit():
    es_repo = _FakeEsRepo([])
    expander = EsChunkExpander(es_repo, "documents", _FakeLogger())

    chunks = await expander.expand([], {}, RoutedScope(), "req-1")

    assert chunks == []
    assert es_repo.captured_query is None
