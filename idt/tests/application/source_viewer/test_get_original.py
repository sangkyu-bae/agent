"""source-passage-viewer module-4 — GetOriginalUseCase (Design §4.2, §7, §8.2 #13 로직)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.knowledge_base.content_browse_guard import KbDocumentContext
from src.application.source_viewer.get_original import GetOriginalUseCase
from src.domain.source_viewer.exceptions import (
    OriginalNotAvailableError,
    UnsupportedOriginalError,
)

_DOC = "8f1c2d3e-0000-4000-8000-000000000001"


def _ctx(filename="규정.pdf"):
    return KbDocumentContext(
        kb_id="kb-1", document_id=_DOC, collection_name="col",
        filename=filename, chunk_strategy="parent_child", kb=MagicMock(),
    )


def _uc(*, filename="규정.pdf", data=b"%PDF", guard_error=None):
    guard = MagicMock()
    guard.ensure = AsyncMock(side_effect=guard_error, return_value=_ctx(filename))
    store = AsyncMock()
    store.open.return_value = data
    return GetOriginalUseCase(guard, store, MagicMock()), guard, store


@pytest.mark.asyncio
async def test_returns_pdf_with_media_type_and_filename():
    uc, guard, store = _uc()
    user = MagicMock()
    result = await uc.execute("kb-1", _DOC, user, "req")
    guard.ensure.assert_awaited_once_with("kb-1", _DOC, user, "req")
    store.open.assert_awaited_once_with(_DOC)
    assert result.content == b"%PDF"
    assert result.media_type == "application/pdf"
    assert result.filename == "규정.pdf"


@pytest.mark.asyncio
async def test_returns_docx_media_type():
    uc, *_ = _uc(filename="계약.docx")
    result = await uc.execute("kb-1", _DOC, MagicMock(), "req")
    assert result.media_type == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [PermissionError("no"), ValueError("Document 'x' not found")])
async def test_guard_errors_propagate_and_skip_store(error):
    uc, _, store = _uc(guard_error=error)
    with pytest.raises(type(error)):
        await uc.execute("kb-1", _DOC, MagicMock(), "req")
    store.open.assert_not_awaited()


@pytest.mark.asyncio
async def test_unsupported_format_raises_before_reading_disk():
    uc, _, store = _uc(filename="규정.hwp")
    with pytest.raises(UnsupportedOriginalError):
        await uc.execute("kb-1", _DOC, MagicMock(), "req")
    store.open.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_original_raises_not_available():
    uc, *_ = _uc(data=None)
    with pytest.raises(OriginalNotAvailableError):
        await uc.execute("kb-1", _DOC, MagicMock(), "req")


@pytest.mark.asyncio
async def test_invalid_document_id_is_not_available():
    uc, _, store = _uc()
    store.open.side_effect = ValueError("document_id must be a UUID")
    with pytest.raises(OriginalNotAvailableError):
        await uc.execute("kb-1", "legacy-id", MagicMock(), "req")
