"""KB 문서 목록 개정 필드·pending_sync — document-revision Design §4.2 #3."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from src.application.knowledge_base.list_documents_use_case import (
    ListKbDocumentsUseCase,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.doc_browse.schemas import KbDocumentSummary
from src.domain.document_revision.value_objects import (
    DocumentVersion,
    RevisionStatus,
    SyncState,
)
from src.domain.knowledge_base.entities import KnowledgeBase
from src.domain.mysql.schemas import MySQLPageResult


def _summary(doc, version=1, lineage=None) -> KbDocumentSummary:
    return KbDocumentSummary(
        document_id=doc, filename=f"{doc}.pdf", chunk_count=1, chunk_strategy="x",
        created_at=datetime(2026, 1, 1), user_id="7", version_no=version,
        version_label="L" if version > 1 else None, lineage_id=lineage,
    )


async def test_list_uses_active_only_and_reports_pending() -> None:
    kb_uc = AsyncMock()
    kb_uc.get.return_value = KnowledgeBase(
        id="kb-1", name="k", owner_id=7, scope=CollectionScope.PERSONAL,
        collection_name="c",
    )
    repo = AsyncMock()
    repo.find_by_kb_id.return_value = MySQLPageResult(
        items=[_summary("v2", 2, "v1"), _summary("solo")], total=2, limit=20, offset=0,
    )
    revision_repo = AsyncMock()
    pending = DocumentVersion(
        document_id="v1", kb_id="kb-1", filename="v1.pdf", lineage_id=None,
        version_no=1, version_label=None, effective_date=None,
        revision_status=RevisionStatus.SUPERSEDED, sync_state=SyncState.PENDING,
        file_hash=None, superseded_by="v2", superseded_at=None, revised_by=None,
        created_at=None,
    )
    revision_repo.find_pending_sync.return_value = [pending]
    uc = ListKbDocumentsUseCase(kb_uc, repo, MagicMock(), revision_repo=revision_repo)
    user = User(email="a@b.c", password_hash="h", role=UserRole.USER,
                status=UserStatus.APPROVED, id=7)

    result = await uc.execute("kb-1", user, "r")

    assert repo.find_by_kb_id.call_args.kwargs["active_only"] is True
    v2 = result.documents[0]
    assert (v2.version_no, v2.version_label, v2.lineage_id, v2.has_history) == (
        2, "L", "v1", True,
    )
    assert result.documents[1].has_history is False
    assert result.pending_sync == [pending]


async def test_list_without_revision_repo_has_empty_pending() -> None:
    kb_uc = AsyncMock()
    kb_uc.get.return_value = KnowledgeBase(
        id="kb-1", name="k", owner_id=7, scope=CollectionScope.PERSONAL,
        collection_name="c",
    )
    repo = AsyncMock()
    repo.find_by_kb_id.return_value = MySQLPageResult(items=[], total=0, limit=20, offset=0)
    uc = ListKbDocumentsUseCase(kb_uc, repo, MagicMock())
    user = User(email="a@b.c", password_hash="h", role=UserRole.USER,
                status=UserStatus.APPROVED, id=7)
    assert (await uc.execute("kb-1", user, "r")).pending_sync == []
