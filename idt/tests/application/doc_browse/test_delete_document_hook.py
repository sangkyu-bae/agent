"""문서 삭제 → DocumentDeletionHook 호출 (graph-rag-foundation §6.2, module-1).

- 저장소 삭제가 끝난 뒤 1회 호출, 실패해도 삭제 결과는 그대로
- 저장소 삭제가 실패해 예외가 나면 훅을 부르지 않는다
"""
import dataclasses
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.application.doc_browse.delete_document_use_case import (
    DeleteDocumentUseCase,
)
from src.domain.doc_browse.policies import DocumentDeletePolicy
from src.domain.extension_hooks import DocumentDeletionHook, ExtensionHooks

from tests.application.doc_browse.test_delete_document_use_case import (
    _make_count_result,
    _make_metadata,
    _make_permission,
)


class _Hook(DocumentDeletionHook):
    def __init__(self, raise_exc=None):
        self.events = []
        self._raise = raise_exc

    async def on_document_deleted(self, event, request_id):
        self.events.append((event, request_id))
        if self._raise:
            raise self._raise


def _uc(hook):
    hooks = ExtensionHooks()
    if hook is not None:
        hooks.register(deletion=hook)
    deps = {
        "metadata_repo": AsyncMock(), "qdrant_client": AsyncMock(),
        "es_repo": AsyncMock(), "permission_service": AsyncMock(),
        "activity_log_service": AsyncMock(), "logger": MagicMock(),
    }
    deps["qdrant_client"].count.return_value = _make_count_result(3)
    deps["es_repo"].delete_by_query.return_value = 3
    uc = DeleteDocumentUseCase(
        document_metadata_repo=deps["metadata_repo"],
        qdrant_client=deps["qdrant_client"],
        es_repo=deps["es_repo"],
        es_index="documents",
        permission_service=deps["permission_service"],
        activity_log_service=deps["activity_log_service"],
        policy=DocumentDeletePolicy(),
        logger=deps["logger"],
        extension_hooks=hooks,
    )
    return uc, deps


@pytest.mark.asyncio
async def test_verified_delete_notifies_hook():
    hook = _Hook()
    uc, _ = _uc(hook)
    await uc.delete_verified(
        "col", "doc-1", "a.pdf", "42", "req-1", extra_detail={"kb_id": "kb-1"}
    )
    event, request_id = hook.events[0]
    assert (event.document_id, event.kb_id, event.collection_name) == (
        "doc-1", "kb-1", "col"
    )
    assert request_id == "req-1"


@pytest.mark.asyncio
async def test_single_delete_notifies_hook_with_metadata_kb():
    hook = _Hook()
    uc, deps = _uc(hook)
    meta = dataclasses.replace(
        _make_metadata(document_id="doc-9", collection_name="col"), kb_id="kb-9"
    )
    deps["metadata_repo"].find_by_document_id.return_value = meta
    deps["permission_service"].find_permission.return_value = _make_permission()
    await uc.execute_single("col", "doc-9", "42", "admin")
    event, _ = hook.events[0]
    assert (event.document_id, event.kb_id) == ("doc-9", "kb-9")


@pytest.mark.asyncio
async def test_hook_error_keeps_delete_result():
    uc, deps = _uc(_Hook(raise_exc=RuntimeError("graph down")))
    result = await uc.delete_verified("col", "doc-1", "a.pdf", "42", "req-1")
    assert result.status == "deleted"
    assert deps["logger"].error.called


@pytest.mark.asyncio
async def test_store_failure_skips_hook():
    hook = _Hook()
    uc, deps = _uc(hook)
    deps["es_repo"].delete_by_query.side_effect = RuntimeError("es down")
    with pytest.raises(DeleteDocumentUseCase.StoreDeleteFailedError):
        await uc.delete_verified("col", "doc-1", "a.pdf", "42", "req-1")
    assert hook.events == []


@pytest.mark.asyncio
async def test_without_hooks_argument_behaves_as_before():
    deps_uc = DeleteDocumentUseCase(
        document_metadata_repo=AsyncMock(), qdrant_client=AsyncMock(),
        es_repo=AsyncMock(), es_index="documents",
        permission_service=AsyncMock(), activity_log_service=AsyncMock(),
        policy=DocumentDeletePolicy(), logger=MagicMock(),
    )
    deps_uc._qdrant_client.count.return_value = _make_count_result(1)
    deps_uc._es_repo.delete_by_query.return_value = 1
    result = await deps_uc.delete_verified("col", "doc-1", "a.pdf", "42", "req-1")
    assert result.status == "deleted"
