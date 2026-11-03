"""DeleteKbDocumentUseCase 단위 테스트 — kb-document-management Design §9.5.

판정 순서: 가드(404/403/404) → 삭제 권한(403) → 요약 잡(409) → 저장소 삭제.
권한·잡 검사에서 막히면 저장소에 손대지 않는다.
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.doc_browse.delete_document_use_case import (
    DeleteDocumentUseCase,
)
from src.application.knowledge_base.content_browse_guard import (
    KbDocumentContext,
)
from src.application.knowledge_base.delete_document_use_case import (
    DeleteKbDocumentUseCase,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.doc_browse.schemas import DeleteDocumentResult
from src.domain.knowledge_base.entities import KnowledgeBase
from src.domain.knowledge_base.policy import KnowledgeBasePolicy
from src.domain.section_summary.entities import (
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_PENDING,
    JOB_STATUS_PROCESSING,
    SectionSummaryJob,
)
from src.domain.section_summary.policy import SectionSummaryJobPolicy

STALE_SECONDS = 600


def _user(user_id: int = 1, role: UserRole = UserRole.USER) -> User:
    return User(
        email="t@t.com",
        password_hash="h",
        role=role,
        status=UserStatus.APPROVED,
        id=user_id,
    )


def _kb(owner_id: int = 1) -> KnowledgeBase:
    return KnowledgeBase(
        id="kb-1",
        name="여신 규정집",
        owner_id=owner_id,
        scope=CollectionScope.PUBLIC,
        collection_name="shared-col",
    )


def _ctx(kb: KnowledgeBase, uploader_id: str = "1") -> KbDocumentContext:
    return KbDocumentContext(
        kb_id="kb-1",
        document_id="doc-1",
        collection_name="shared-col",
        filename="a.pdf",
        chunk_strategy="parent_child",
        kb=kb,
        uploader_id=uploader_id,
    )


def _job(status: str, updated_ago_seconds: int = 0) -> SectionSummaryJob:
    return SectionSummaryJob(
        id="job-1",
        document_id="doc-1",
        kb_id="kb-1",
        collection_name="shared-col",
        chunking_profile_id="p-1",
        llm_model_id="m-1",
        embedding_provider="openai",
        embedding_model="e-1",
        status=status,
        updated_at=datetime.now() - timedelta(seconds=updated_ago_seconds),
    )


def _result() -> DeleteDocumentResult:
    return DeleteDocumentResult(
        document_id="doc-1",
        collection_name="shared-col",
        filename="a.pdf",
        deleted_qdrant_chunks=4,
        deleted_es_chunks=4,
        status="deleted",
    )


def _make_use_case(ctx=None, job=None):
    guard = AsyncMock()
    guard.ensure.return_value = ctx or _ctx(_kb())
    deleter = AsyncMock()
    deleter.delete_verified.return_value = _result()
    job_repo = AsyncMock()
    job_repo.find_by_document.return_value = job
    use_case = DeleteKbDocumentUseCase(
        guard=guard,
        deleter=deleter,
        job_repo=job_repo,
        policy=KnowledgeBasePolicy(),
        job_policy=SectionSummaryJobPolicy(),
        logger=MagicMock(),
        stale_seconds=STALE_SECONDS,
    )
    return use_case, guard, deleter, job_repo


class TestExecute:
    @pytest.mark.asyncio
    async def test_owner_deletes_and_job_row_removed(self):
        use_case, guard, deleter, job_repo = _make_use_case(
            ctx=_ctx(_kb(owner_id=1), uploader_id="55"),
            job=_job(JOB_STATUS_COMPLETED),
        )

        result = await use_case.execute("kb-1", "doc-1", _user(1), "req-1")

        assert result.deleted_qdrant_chunks == 4
        guard.ensure.assert_awaited_once()
        deleter.delete_verified.assert_awaited_once_with(
            "shared-col",
            "doc-1",
            "a.pdf",
            "1",
            "req-1",
            extra_detail={"kb_id": "kb-1"},
        )
        job_repo.delete_by_document.assert_awaited_once_with("doc-1", "req-1")

    @pytest.mark.asyncio
    async def test_uploader_can_delete(self):
        use_case, _, deleter, _ = _make_use_case(
            ctx=_ctx(_kb(owner_id=99), uploader_id="7")
        )
        await use_case.execute("kb-1", "doc-1", _user(7), "req-1")
        deleter.delete_verified.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_admin_can_delete(self):
        use_case, _, deleter, _ = _make_use_case(
            ctx=_ctx(_kb(owner_id=99), uploader_id="55")
        )
        await use_case.execute(
            "kb-1", "doc-1", _user(7, UserRole.ADMIN), "req-1"
        )
        deleter.delete_verified.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reader_denied_before_any_store_access(self):
        """읽기 가능한 PUBLIC 열람자도 삭제 단계에서 막힌다."""
        use_case, _, deleter, job_repo = _make_use_case(
            ctx=_ctx(_kb(owner_id=99), uploader_id="55")
        )

        with pytest.raises(PermissionError):
            await use_case.execute("kb-1", "doc-1", _user(7), "req-1")

        job_repo.find_by_document.assert_not_awaited()
        deleter.delete_verified.assert_not_awaited()
        job_repo.delete_by_document.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_guard_error_propagates_first(self):
        use_case, guard, deleter, job_repo = _make_use_case()
        guard.ensure.side_effect = ValueError("not found")

        with pytest.raises(ValueError, match="not found"):
            await use_case.execute("kb-1", "doc-x", _user(1), "req-1")

        job_repo.find_by_document.assert_not_awaited()
        deleter.delete_verified.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "status", [JOB_STATUS_PENDING, JOB_STATUS_PROCESSING]
    )
    async def test_active_job_blocks(self, status):
        use_case, _, deleter, job_repo = _make_use_case(job=_job(status))

        with pytest.raises(DeleteKbDocumentUseCase.DocumentBusyError):
            await use_case.execute("kb-1", "doc-1", _user(1), "req-1")

        deleter.delete_verified.assert_not_awaited()
        job_repo.delete_by_document.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_stale_job_does_not_block(self):
        use_case, _, deleter, job_repo = _make_use_case(
            job=_job(JOB_STATUS_PROCESSING, STALE_SECONDS + 60)
        )

        await use_case.execute("kb-1", "doc-1", _user(1), "req-1")

        deleter.delete_verified.assert_awaited_once()
        job_repo.delete_by_document.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "job", [None, _job(JOB_STATUS_COMPLETED), _job(JOB_STATUS_FAILED)]
    )
    async def test_inactive_job_does_not_block(self, job):
        use_case, _, deleter, _ = _make_use_case(job=job)

        await use_case.execute("kb-1", "doc-1", _user(1), "req-1")

        deleter.delete_verified.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_store_failure_keeps_job_row(self):
        use_case, _, deleter, job_repo = _make_use_case()
        deleter.delete_verified.side_effect = (
            DeleteDocumentUseCase.StoreDeleteFailedError("es down")
        )

        with pytest.raises(DeleteDocumentUseCase.StoreDeleteFailedError):
            await use_case.execute("kb-1", "doc-1", _user(1), "req-1")

        job_repo.delete_by_document.assert_not_awaited()


def test_delete_verified_called_only_from_kb_use_case():
    """delete_verified는 권한을 검사하지 않으므로 호출 지점을 하나로 제한한다 (§7)."""
    src_root = Path(__file__).resolve().parents[3] / "src"
    callers = []
    for path in src_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "delete_verified"
            ):
                callers.append(path.relative_to(src_root).as_posix())

    assert callers == ["application/knowledge_base/delete_document_use_case.py"]
