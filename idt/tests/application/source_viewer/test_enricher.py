"""source-passage-viewer module-3 — SourceViewerEnricher (Design §2.2, §6, §8.2 #6~8)."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.source_viewer.enricher import SourceViewerEnricher
from src.domain.agent_run.entities import RetrievalSource
from src.domain.agent_run.source_policy import RunEvidence, RunSourceItem, SourceKind
from src.domain.agent_run.value_objects import RunId

_DOC = "8f1c2d3e-0000-4000-8000-000000000001"
_RUN = RunId("00000000-0000-4000-8000-0000000000aa")


def _r(rid, *, chunk_id, kb_id="kb-1", filename="규정.pdf", page=3, collection="kb"):
    meta = {"chunk_id": chunk_id, "page": page}
    if kb_id:
        meta["kb_id"] = kb_id
    if filename:
        meta["filename"] = filename
    return RetrievalSource(
        id=rid, run_id=_RUN, tool_call_id=None, collection_name=collection,
        document_id=_DOC, chunk_id=chunk_id, score=0.5, rank_index=1,
        content_preview=f"발췌-{chunk_id}", metadata_json=meta,
        created_at=datetime(2026, 11, 19),
    )


def _evidence(retrievals, filenames=None):
    return RunEvidence(
        retrievals=retrievals, tool_calls=[], filenames=filenames or {}, mcp_tools={},
    )


def _doc_item(key=_DOC):
    return RunSourceItem(kind=SourceKind.DOCUMENT, label="규정.pdf", excerpt="발췌", key=key)


def _web_item():
    return RunSourceItem(
        kind=SourceKind.WEB, label="site", excerpt="웹", key="https://a.b", url="https://a.b",
    )


def _enricher(store=None):
    return SourceViewerEnricher(store, MagicMock())


@pytest.mark.asyncio
async def test_document_item_gets_viewer_with_passages():
    store = AsyncMock()
    store.exists.return_value = True
    evidence = _evidence([_r("r1", chunk_id="c-1"), _r("r2", chunk_id="c-2", page=9)])
    (item,) = await _enricher(store).enrich([_doc_item()], evidence, "req")
    assert item.viewer["document_id"] == _DOC
    assert item.viewer["kb_id"] == "kb-1"
    assert item.viewer["original"] == "pdf"
    assert [p["chunk_id"] for p in item.viewer["passages"]] == ["c-1", "c-2"]
    assert item.to_payload()["viewer"] == item.viewer


@pytest.mark.asyncio
async def test_web_item_untouched():
    evidence = _evidence([_r("r1", chunk_id="c-1")])
    items = [_web_item()]
    assert await _enricher(AsyncMock()).enrich(items, evidence, "req") == items


@pytest.mark.asyncio
async def test_document_without_kb_id_has_no_viewer():
    evidence = _evidence([_r("r1", chunk_id="c-1", kb_id=None)])
    (item,) = await _enricher(AsyncMock()).enrich([_doc_item()], evidence, "req")
    assert item.viewer is None
    assert "viewer" not in item.to_payload()


@pytest.mark.asyncio
async def test_item_key_not_matching_any_retrieval_has_no_viewer():
    evidence = _evidence([_r("r1", chunk_id="c-1")])
    (item,) = await _enricher(AsyncMock()).enrich([_doc_item("other")], evidence, "req")
    assert item.viewer is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exists, filename, expected",
    [(True, "규정.pdf", "pdf"), (True, "계약.docx", "docx"), (True, "규정.hwp", None), (False, "규정.pdf", None)],
)
async def test_original_kind_depends_on_store_and_format(exists, filename, expected):
    store = AsyncMock()
    store.exists.return_value = exists
    evidence = _evidence([_r("r1", chunk_id="c-1", filename=filename)])
    (item,) = await _enricher(store).enrich([_doc_item()], evidence, "req")
    assert item.viewer["original"] == expected


@pytest.mark.asyncio
async def test_unsupported_format_skips_store_lookup():
    store = AsyncMock()
    evidence = _evidence([_r("r1", chunk_id="c-1", filename="규정.hwp")])
    await _enricher(store).enrich([_doc_item()], evidence, "req")
    store.exists.assert_not_awaited()


@pytest.mark.asyncio
async def test_without_store_viewer_is_text_only():
    evidence = _evidence([_r("r1", chunk_id="c-1")])
    (item,) = await _enricher(None).enrich([_doc_item()], evidence, "req")
    assert item.viewer["original"] is None


@pytest.mark.asyncio
async def test_filename_from_lookup_when_metadata_lacks_it():
    store = AsyncMock()
    store.exists.return_value = True
    evidence = _evidence([_r("r1", chunk_id="c-1", filename=None)], {_DOC: "계약.docx"})
    (item,) = await _enricher(store).enrich([_doc_item()], evidence, "req")
    assert item.viewer["original"] == "docx"


@pytest.mark.asyncio
async def test_store_failure_only_drops_original():
    store = AsyncMock()
    store.exists.side_effect = OSError("disk")
    enricher = _enricher(store)
    evidence = _evidence([_r("r1", chunk_id="c-1")])
    (item,) = await enricher.enrich([_doc_item()], evidence, "req")
    assert item.viewer["original"] is None
    assert item.viewer["passages"]


@pytest.mark.asyncio
async def test_unexpected_failure_returns_input_unchanged():
    enricher = _enricher(AsyncMock())
    items = [_doc_item()]
    broken = MagicMock()
    broken.retrievals = None  # 정책이 순회 중 TypeError
    assert await enricher.enrich(items, broken, "req") == items
