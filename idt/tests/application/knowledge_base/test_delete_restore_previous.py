"""KB 문서 삭제 restore_previous — document-revision Design §4.2 #9 (근거 공백 방지)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.knowledge_base.content_browse_guard import KbDocumentContext
from src.application.knowledge_base.delete_document_use_case import (
    DeleteKbDocumentUseCase,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.doc_browse.schemas import DeleteDocumentResult
from src.domain.document_revision.value_objects import (
    DocumentVersion,
    RevisionStatus,
    SyncState,
)
from src.domain.knowledge_base.entities import KnowledgeBase
from src.domain.knowledge_base.policy import KnowledgeBasePolicy
from src.domain.section_summary.policy import SectionSummaryJobPolicy


def _v(doc, version=1, lineage=None, status=RevisionStatus.ACTIVE):
    return DocumentVersion(
        document_id=doc, kb_id="kb-1", filename=f"{doc}.pdf", lineage_id=lineage,
        version_no=version, version_label=None, effective_date=None,
        revision_status=status, sync_state=SyncState.SYNCED, file_hash=None,
        superseded_by=None, superseded_at=None, revised_by=None, created_at=None,
    )


@pytest.fixture
def parts():
    calls: list[str] = []
    guard = AsyncMock()
    guard.ensure.return_value = KbDocumentContext(
        kb_id="kb-1", document_id="v2", collection_name="col", filename="v2.pdf",
        chunk_strategy="x",
        kb=KnowledgeBase(id="kb-1", name="k", owner_id=7,
                         scope=CollectionScope.PERSONAL, collection_name="col"),
        uploader_id="7",
    )
    deleter = AsyncMock()

    async def _delete(*a, **k):
        calls.append("delete")
        return DeleteDocumentResult(
            document_id="v2", collection_name="col", filename="v2.pdf",
            deleted_qdrant_chunks=3, deleted_es_chunks=3, status="deleted",
        )

    deleter.delete_verified.side_effect = _delete
    job_repo = AsyncMock()
    job_repo.find_by_document.return_value = None
    repo = AsyncMock()
    repo.find_version.return_value = _v("v2", 2, "v1")
    repo.find_lineage_versions.return_value = [
        _v("v1", status=RevisionStatus.SUPERSEDED), _v("v2", 2, "v1"),
    ]
    supersede = AsyncMock()

    async def _reactivate(*a, **k):
        calls.append("reactivate")
        return SyncState.SYNCED

    supersede.reactivate.side_effect = _reactivate
    uc = DeleteKbDocumentUseCase(
        guard=guard, deleter=deleter, job_repo=job_repo,
        policy=KnowledgeBasePolicy(), job_policy=SectionSummaryJobPolicy(),
        logger=MagicMock(), stale_seconds=600,
        revision_repo=repo, supersede_service=supersede,
    )
    user = User(email="a@b.c", password_hash="h", role=UserRole.USER,
                status=UserStatus.APPROVED, id=7)
    return uc, calls, repo, supersede, user


async def test_restore_previous_reactivates_before_delete(parts) -> None:
    uc, calls, _, supersede, user = parts
    result = await uc.execute("kb-1", "v2", user, "r", restore_previous=True)
    assert calls == ["reactivate", "delete"]
    supersede.reactivate.assert_awaited_once_with("v1", "col", request_id="r")
    assert result.restored_document_id == "v1"


async def test_default_does_not_restore(parts) -> None:
    uc, calls, _, supersede, user = parts
    result = await uc.execute("kb-1", "v2", user, "r")
    assert calls == ["delete"]
    supersede.reactivate.assert_not_awaited()
    assert result.restored_document_id is None


async def test_deleting_superseded_version_restores_nothing(parts) -> None:
    uc, calls, repo, supersede, user = parts
    repo.find_version.return_value = _v("v1", status=RevisionStatus.SUPERSEDED)
    result = await uc.execute("kb-1", "v1", user, "r", restore_previous=True)
    supersede.reactivate.assert_not_awaited()
    assert result.restored_document_id is None


async def test_check_then_delete_checked(parts) -> None:
    uc, calls, _, _, user = parts
    ctx = await uc.check("kb-1", "v2", user, "r")
    result = await uc.delete_checked(ctx, user, "r")
    assert calls == ["delete"] and result.document_id == "v2"


async def test_restore_pending_blocks_delete_and_reverts_marks(parts) -> None:
    """Act-1 (Gap I2): 재활성 표식 실패면 삭제를 멈추고 이전 버전 표식을 되돌린 뒤 409."""
    from src.domain.document_revision.errors import RestorePendingError

    uc, calls, repo, supersede, user = parts

    async def _pending(*a, **k):
        calls.append("reactivate")
        return SyncState.PENDING

    supersede.reactivate.side_effect = _pending
    with pytest.raises(RestorePendingError):
        await uc.execute("kb-1", "v2", user, "r", restore_previous=True)
    assert "delete" not in calls
    reverted = supersede.resync.call_args.args[0]
    assert reverted.document_id == "v1"
    assert reverted.revision_status is RevisionStatus.SUPERSEDED
