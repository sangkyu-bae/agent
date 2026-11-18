"""KB 업로드 → PostIngestHook 호출 (graph-rag-foundation §2.2 적재, module-1).

- 훅 미등록이면 아무것도 하지 않는다(기존 동작)
- 등록되면 업로드 결과로 만든 이벤트를 1회 넘긴다
- 훅 예외는 업로드 결과를 바꾸지 않는다(§6.2)
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.application.knowledge_base.upload_use_case import (
    KnowledgeBaseUploadUseCase,
)
from src.domain.extension_hooks import ExtensionHooks, PostIngestHook
from src.domain.knowledge_base.policy import KnowledgeBasePolicy

from tests.application.knowledge_base.test_upload_summary_kickoff import (
    _kb,
    _upload_result,
    _user,
)


class _Hook(PostIngestHook):
    def __init__(self, raise_exc=None):
        self.events = []
        self._raise = raise_exc

    async def on_document_ingested(self, event, request_id):
        self.events.append((event, request_id))
        if self._raise:
            raise self._raise


def _use_case(hooks, status="completed"):
    kb_repo = AsyncMock()
    kb_repo.find_by_id.return_value = _kb()
    dept_repo = AsyncMock()
    dept_repo.find_departments_by_user.return_value = []
    unified = AsyncMock()
    unified.execute.return_value = _upload_result(status)
    logger = MagicMock()
    uc = KnowledgeBaseUploadUseCase(
        kb_repo=kb_repo, policy=KnowledgeBasePolicy(), dept_repo=dept_repo,
        unified_upload=unified, logger=logger, extension_hooks=hooks,
    )
    return uc, logger


async def _run(uc, filename="rule.pdf"):
    return await uc.execute(
        kb_id="kb-1", user=_user(), file_bytes=b"x", filename=filename,
        request_id="req-1",
    )


@pytest.mark.asyncio
async def test_no_hooks_object_is_noop():
    uc, _ = _use_case(None)
    result, _, _ = await _run(uc)
    assert result.status == "completed"


@pytest.mark.asyncio
async def test_hook_receives_event():
    hook = _Hook()
    hooks = ExtensionHooks()
    hooks.register(post_ingest=hook)
    uc, _ = _use_case(hooks)
    await _run(uc)
    assert len(hook.events) == 1
    event, request_id = hook.events[0]
    assert request_id == "req-1"
    assert event.document_id == "doc-1"
    assert event.kb_id == "kb-1"
    assert event.collection_name == "col"
    assert event.filename == "rule.pdf"
    assert event.user_id == "1"
    assert event.chunk_count == 2
    assert event.status == "completed"


@pytest.mark.asyncio
async def test_failed_upload_still_notifies_with_status():
    # 실행 여부(실패 건 무시)는 확장 모듈이 status 로 판단한다
    hook = _Hook()
    hooks = ExtensionHooks()
    hooks.register(post_ingest=hook)
    uc, _ = _use_case(hooks, status="failed")
    await _run(uc)
    assert hook.events[0][0].status == "failed"


@pytest.mark.asyncio
async def test_hook_error_does_not_break_upload():
    hooks = ExtensionHooks()
    hooks.register(post_ingest=_Hook(raise_exc=RuntimeError("boom")))
    uc, logger = _use_case(hooks)
    result, kb, _ = await _run(uc)
    assert result.status == "completed"
    assert kb.id == "kb-1"
    assert logger.error.called
