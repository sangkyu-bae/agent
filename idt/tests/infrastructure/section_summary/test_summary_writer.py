"""DualStoreSummaryWriter 테스트 — 결정적 ID·ES 필드 격리·저장 순서 (Design D5/D6/D7)."""
import pytest

from src.domain.section_summary.entities import SectionSummaryRecord
from src.infrastructure.section_summary.summary_writer import (
    DualStoreSummaryWriter,
    summary_id_for,
)


class _FakeLogger:
    def debug(self, *a, **k): ...
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...
    def critical(self, *a, **k): ...


class _FakeEsRepo:
    def __init__(self, order):
        self.docs = []
        self._order = order

    async def index(self, document, request_id):
        self._order.append("es")
        self.docs.append(document)
        return document.id


class _FakeQdrantClient:
    def __init__(self, order):
        self.upserts = []
        self._order = order

    async def upsert(self, collection_name, points):
        self._order.append("qdrant")
        self.upserts.append((collection_name, points))


def _record() -> SectionSummaryRecord:
    return SectionSummaryRecord(
        summary_id=summary_id_for("parent-1"),
        section_ref="parent-1",
        document_id="doc-1",
        collection_name="col",
        kb_id="kb-1",
        kb_name="여신규정",
        user_id="7",
        clause_title="제1조 (목적)",
        chunk_index=0,
        keywords=["여신", "규정"],
        summary_text="a\nb\nc",
        vector=[0.1, 0.2],
        filename="rule.pdf",
    )


def test_summary_id_is_deterministic():
    assert summary_id_for("parent-1") == summary_id_for("parent-1")
    assert summary_id_for("parent-1") != summary_id_for("parent-2")


@pytest.mark.asyncio
async def test_write_es_first_then_qdrant():
    order: list[str] = []
    es_repo = _FakeEsRepo(order)
    client = _FakeQdrantClient(order)
    writer = DualStoreSummaryWriter(client, es_repo, "documents", _FakeLogger())

    await writer.write(_record(), "req-1")

    assert order == ["es", "qdrant"]


@pytest.mark.asyncio
async def test_es_document_has_no_bm25_fields():
    """content/morph_text/morph_keywords 부재 → 기존 BM25 미노출 (D7)."""
    order: list[str] = []
    es_repo = _FakeEsRepo(order)
    writer = DualStoreSummaryWriter(
        _FakeQdrantClient(order), es_repo, "documents", _FakeLogger()
    )
    await writer.write(_record(), "req-1")

    doc = es_repo.docs[0]
    assert doc.id == summary_id_for("parent-1")
    assert doc.index == "documents"
    body = doc.body
    for forbidden in ("content", "morph_text", "morph_keywords"):
        assert forbidden not in body
    assert body["chunk_type"] == "section_summary"
    assert body["section_ref"] == "parent-1"
    assert body["summary_text"] == "a\nb\nc"
    assert body["summary_keywords"] == ["여신", "규정"]
    assert body["document_id"] == "doc-1"
    assert body["kb_id"] == "kb-1"


@pytest.mark.asyncio
async def test_qdrant_payload_contract():
    order: list[str] = []
    client = _FakeQdrantClient(order)
    writer = DualStoreSummaryWriter(
        client, _FakeEsRepo(order), "documents", _FakeLogger()
    )
    record = _record()
    await writer.write(record, "req-1")

    collection, points = client.upserts[0]
    assert collection == "col"
    point = points[0]
    assert point.id == record.summary_id
    assert point.vector == [0.1, 0.2]
    payload = point.payload
    assert payload["chunk_type"] == "section_summary"
    assert payload["section_ref"] == "parent-1"
    assert payload["document_id"] == "doc-1"
    assert payload["keywords"] == ["여신", "규정"]
    assert payload["summary"] == "a\nb\nc"
    assert payload["content"] == "a\nb\nc"
    assert payload["clause_title"] == "제1조 (목적)"
