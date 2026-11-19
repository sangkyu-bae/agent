"""source-passage-viewer module-2 — 문서 삭제 → original_sink.delete (Design §2.2, §8.2 #12).

- 단건·검증 삭제 모두 저장소 삭제 뒤 1회 호출(_notify_deleted 한 지점)
- sink 예외는 삭제 결과를 바꾸지 않는다
- 미주입이면 기존 동작 그대로
"""
import dataclasses
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.doc_browse.delete_document_use_case import DeleteDocumentUseCase
from src.domain.doc_browse.policies import DocumentDeletePolicy
from tests.application.doc_browse.test_delete_document_use_case import (
    _make_count_result,
    _make_metadata,
    _make_permission,
)


def _uc(sink):
    deps = {
        "metadata_repo": AsyncMock(), "qdrant_client": AsyncMock(),
        "es_repo": AsyncMock(), "permission_service": AsyncMock(),
        "activity_log_service": AsyncMock(), "logger": MagicMock(),
    }
    deps["qdrant_client"].count.return_value = _make_count_result(3)
    deps["es_repo"].delete_by_query.return_value = 3
    kwargs = dict(
        document_metadata_repo=deps["metadata_repo"],
        qdrant_client=deps["qdrant_client"],
        es_repo=deps["es_repo"],
        es_index="documents",
        permission_service=deps["permission_service"],
        activity_log_service=deps["activity_log_service"],
        policy=DocumentDeletePolicy(),
        logger=deps["logger"],
    )
    if sink is not None:
        kwargs["original_sink"] = sink
    return DeleteDocumentUseCase(**kwargs), deps


@pytest.mark.asyncio
async def test_verified_delete_removes_original():
    sink = AsyncMock()
    uc, _ = _uc(sink)
    result = await uc.delete_verified("col", "doc-1", "a.pdf", "42", "req-1")
    assert result.status == "deleted"
    sink.delete.assert_awaited_once_with("doc-1", "req-1")


@pytest.mark.asyncio
async def test_single_delete_removes_original():
    sink = AsyncMock()
    uc, deps = _uc(sink)
    meta = dataclasses.replace(
        _make_metadata(document_id="doc-9", collection_name="col"), kb_id="kb-9"
    )
    deps["metadata_repo"].find_by_document_id.return_value = meta
    deps["permission_service"].find_permission.return_value = _make_permission()
    await uc.execute_single("col", "doc-9", "42", "admin")
    assert sink.delete.await_count == 1
    assert sink.delete.await_args.args[0] == "doc-9"


@pytest.mark.asyncio
async def test_sink_failure_does_not_change_delete_result():
    sink = AsyncMock()
    sink.delete.side_effect = RuntimeError("boom")
    uc, deps = _uc(sink)
    result = await uc.delete_verified("col", "doc-1", "a.pdf", "42", "req-1")
    assert result.status == "deleted"
    deps["logger"].warning.assert_called()


@pytest.mark.asyncio
async def test_without_sink_delete_is_unchanged():
    uc, _ = _uc(None)
    result = await uc.delete_verified("col", "doc-1", "a.pdf", "42", "req-1")
    assert result.status == "deleted"


@pytest.mark.asyncio
async def test_store_failure_skips_original_delete():
    sink = AsyncMock()
    uc, deps = _uc(sink)
    deps["es_repo"].delete_by_query.side_effect = RuntimeError("es down")
    with pytest.raises(DeleteDocumentUseCase.StoreDeleteFailedError):
        await uc.delete_verified("col", "doc-1", "a.pdf", "42", "req-1")
    sink.delete.assert_not_awaited()
