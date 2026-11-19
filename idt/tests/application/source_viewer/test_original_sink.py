"""source-passage-viewer module-2 — OriginalSink 예외 흡수 (Design §6)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.source_viewer.original_sink import OriginalSink

_DOC = "8f1c2d3e-0000-4000-8000-000000000001"


def _sink(store=None):
    store = store or AsyncMock()
    logger = MagicMock()
    return OriginalSink(store, logger), store, logger


@pytest.mark.asyncio
@pytest.mark.parametrize("filename", ["규정.pdf", "계약.DOCX"])
async def test_save_supported_formats(filename):
    sink, store, _ = _sink()
    await sink.save(_DOC, filename, b"data", "req-1")
    store.save.assert_awaited_once_with(_DOC, b"data")


@pytest.mark.asyncio
@pytest.mark.parametrize("filename", ["규정.hwp", "표.xlsx", "메모.txt", ""])
async def test_save_skips_unsupported_formats(filename):
    sink, store, _ = _sink()
    await sink.save(_DOC, filename, b"data", "req-1")
    store.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_failure_is_absorbed_and_logged():
    store = AsyncMock()
    store.save.side_effect = OSError("disk full")
    sink, _, logger = _sink(store)
    await sink.save(_DOC, "a.pdf", b"data", "req-1")
    logger.warning.assert_called_once()
    assert logger.warning.call_args.kwargs["request_id"] == "req-1"


@pytest.mark.asyncio
async def test_save_invalid_document_id_is_absorbed():
    from src.infrastructure.source_viewer.local_disk_store import LocalDiskOriginalStore

    sink, _, logger = _sink(LocalDiskOriginalStore.__new__(LocalDiskOriginalStore))
    await sink.save("../escape", "a.pdf", b"data", "req-1")
    logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_delete_calls_store():
    sink, store, _ = _sink()
    await sink.delete(_DOC, "req-1")
    store.delete.assert_awaited_once_with(_DOC)


@pytest.mark.asyncio
async def test_delete_failure_is_absorbed_and_logged():
    store = AsyncMock()
    store.delete.side_effect = PermissionError("locked")
    sink, _, logger = _sink(store)
    await sink.delete(_DOC, "req-1")
    logger.warning.assert_called_once()
