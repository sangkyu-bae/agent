"""SupersedeService — 순서 고정·실패 시 pending (Design §1.2, §2.2)."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.document_revision.supersede_service import SupersedeService
from src.domain.document_revision.value_objects import (
    ChunkMarkResult,
    DocumentVersion,
    RevisionStatus,
    SyncState,
)

NOW = datetime(2026, 11, 23, 12, 0)


def _old() -> DocumentVersion:
    return DocumentVersion(
        document_id="old", kb_id="kb-1", filename="a.pdf", lineage_id=None,
        version_no=1, version_label=None, effective_date=None,
        revision_status=RevisionStatus.ACTIVE, sync_state=SyncState.SYNCED,
        file_hash=None, superseded_by=None, superseded_at=None, revised_by=None,
        created_at=None,
    )


def _service(mark_result=ChunkMarkResult(True, True), mark_raises=None):
    repo = AsyncMock()
    marker = MagicMock()
    marker.mark = AsyncMock(return_value=mark_result, side_effect=mark_raises)
    calls: list[str] = []
    repo.set_status.side_effect = lambda *a, **k: calls.append("set_status")
    repo.set_sync_state.side_effect = lambda *a, **k: calls.append("set_sync")

    async def _mark(*a, **k):
        calls.append("mark")
        if mark_raises:
            raise mark_raises
        return mark_result

    marker.mark = AsyncMock(side_effect=_mark)
    svc = SupersedeService(repo, marker, MagicMock(), clock=lambda: NOW)
    return svc, repo, marker, calls


@pytest.mark.asyncio
async def test_supersede_order_and_synced() -> None:
    svc, repo, marker, calls = _service()
    state = await svc.supersede(_old(), "new", "col", revised_by="7", request_id="r")

    assert state is SyncState.SYNCED
    assert calls == ["set_status", "mark", "set_sync"]
    kwargs = repo.set_status.call_args.kwargs
    assert repo.set_status.call_args.args[0] == "old"
    assert kwargs["status"] is RevisionStatus.SUPERSEDED
    assert kwargs["sync_state"] is SyncState.PENDING
    assert (kwargs["superseded_by"], kwargs["superseded_at"], kwargs["revised_by"]) == (
        "new", NOW, "7",
    )
    marker.mark.assert_awaited_once_with("col", "old", RevisionStatus.SUPERSEDED, "r")
    repo.set_sync_state.assert_awaited_once_with("old", SyncState.SYNCED, "r")


@pytest.mark.asyncio
async def test_partial_mark_leaves_pending() -> None:
    svc, repo, _, calls = _service(mark_result=ChunkMarkResult(True, False))
    state = await svc.supersede(_old(), "new", "col", revised_by="7", request_id="r")
    assert state is SyncState.PENDING
    assert calls == ["set_status", "mark"]
    repo.set_sync_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_marker_exception_leaves_pending() -> None:
    svc, repo, _, _ = _service(mark_raises=RuntimeError("down"))
    state = await svc.supersede(_old(), "new", "col", revised_by="7", request_id="r")
    assert state is SyncState.PENDING
    repo.set_sync_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_reactivate_sets_active_then_marks() -> None:
    svc, repo, marker, calls = _service()
    state = await svc.reactivate("old", "col", request_id="r")
    assert state is SyncState.SYNCED
    assert calls == ["set_status", "mark", "set_sync"]
    kwargs = repo.set_status.call_args.kwargs
    assert kwargs["status"] is RevisionStatus.ACTIVE
    assert kwargs["superseded_by"] is None and kwargs["superseded_at"] is None
    marker.mark.assert_awaited_once_with("col", "old", RevisionStatus.ACTIVE, "r")


@pytest.mark.asyncio
async def test_resync_uses_current_status() -> None:
    svc, repo, marker, calls = _service()
    v = _old()
    superseded = DocumentVersion(**{**v.__dict__, "revision_status": RevisionStatus.SUPERSEDED})
    state = await svc.resync(superseded, "col", request_id="r")
    assert state is SyncState.SYNCED
    assert calls == ["mark", "set_sync"]
    marker.mark.assert_awaited_once_with("col", "old", RevisionStatus.SUPERSEDED, "r")
