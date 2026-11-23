"""KnowledgeBaseUploadUseCase 개정 통합 — document-revision Design §2.2·§4.2 #2 (Plan SC-2)."""
import hashlib
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.document_revision.schemas import RevisionUploadOptions
from src.application.knowledge_base.upload_use_case import KnowledgeBaseUploadUseCase
from src.application.unified_upload.schemas import (
    EsStoreResult,
    QdrantStoreResult,
    UnifiedUploadResult,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.document_revision.errors import (
    DuplicateDocumentError,
    RevisionTargetInvalidError,
)
from src.domain.document_revision.value_objects import (
    CheckDecision,
    DocumentVersion,
    RevisionStatus,
    SyncState,
)
from src.domain.knowledge_base.entities import KnowledgeBase
from src.domain.knowledge_base.policy import KnowledgeBasePolicy

KB_ID = "kb-1"
FILE = b"%PDF-1.4 new edition"
HASH = hashlib.sha256(FILE).hexdigest()


def _user() -> User:
    return User(
        email="a@b.c", password_hash="h", role=UserRole.USER,
        status=UserStatus.APPROVED, id=7,
    )


def _kb() -> KnowledgeBase:
    return KnowledgeBase(
        id=KB_ID, name="규정", owner_id=7, scope=CollectionScope.PERSONAL,
        collection_name="col",
    )


def _v(doc_id, version=1, lineage=None, status=RevisionStatus.ACTIVE, kb=KB_ID):
    return DocumentVersion(
        document_id=doc_id, kb_id=kb, filename=f"{doc_id}.pdf", lineage_id=lineage,
        version_no=version, version_label=None, effective_date=None,
        revision_status=status, sync_state=SyncState.SYNCED, file_hash=None,
        superseded_by=None, superseded_at=None, revised_by=None, created_at=None,
    )


def _result(status="completed") -> UnifiedUploadResult:
    return UnifiedUploadResult(
        document_id="new", filename="규정_v3.pdf", total_pages=1, chunk_count=2,
        collection_name="col",
        qdrant=QdrantStoreResult(stored_ids=["a"], embedding_model="m"),
        es=EsStoreResult(indexed_count=2), chunking_config={}, status=status,
    )


@pytest.fixture
def deps():
    kb_repo = AsyncMock()
    kb_repo.find_by_id.return_value = _kb()
    dept_repo = AsyncMock()
    dept_repo.find_departments_by_user.return_value = []
    unified = AsyncMock()
    unified.execute.return_value = _result()
    revision_repo = AsyncMock()
    revision_repo.find_by_hash.return_value = []
    supersede = AsyncMock()
    supersede.supersede.return_value = SyncState.SYNCED
    check_log = AsyncMock()
    uc = KnowledgeBaseUploadUseCase(
        kb_repo=kb_repo, policy=KnowledgeBasePolicy(), dept_repo=dept_repo,
        unified_upload=unified, logger=MagicMock(),
        revision_repo=revision_repo, supersede_service=supersede,
        check_log_repo=check_log,
    )
    return uc, unified, revision_repo, supersede, check_log


async def _run(uc, revision=None):
    return await uc.execute_with_revision(
        KB_ID, _user(), FILE, "규정_v3.pdf", "r", revision=revision
    )


class TestHashAndDuplicate:
    async def test_hash_is_stored_on_new_document(self, deps) -> None:
        uc, unified, revision_repo, _, _ = deps
        outcome = await _run(uc)
        req = unified.execute.call_args.args[0]
        assert req.file_hash == HASH
        assert (req.lineage_id, req.version_no) == (None, 1)
        revision_repo.find_by_hash.assert_awaited_once_with(KB_ID, HASH, "r")
        assert outcome.revision.applied is False
        assert outcome.revision.reason is None

    async def test_duplicate_blocks_before_ingest(self, deps) -> None:
        uc, unified, revision_repo, _, _ = deps
        revision_repo.find_by_hash.return_value = [_v("old")]
        with pytest.raises(DuplicateDocumentError) as e:
            await _run(uc)
        assert e.value.existing.document_id == "old"
        unified.execute.assert_not_awaited()

    async def test_duplicate_prefers_active_match(self, deps) -> None:
        uc, _, revision_repo, _, _ = deps
        revision_repo.find_by_hash.return_value = [
            _v("v1", status=RevisionStatus.SUPERSEDED), _v("v2", 2, lineage="v1"),
        ]
        with pytest.raises(DuplicateDocumentError) as e:
            await _run(uc)
        assert e.value.existing.document_id == "v2"

    async def test_legacy_tuple_execute_still_works(self, deps) -> None:
        uc, _, _, _, _ = deps
        result, kb, summary = await uc.execute(KB_ID, _user(), FILE, "a.pdf", "r")
        assert result.document_id == "new" and kb.id == KB_ID


class TestSupersede:
    async def test_confirmed_revision_ingests_next_version_then_supersedes(self, deps) -> None:
        uc, unified, revision_repo, supersede, check_log = deps
        old = _v("v2", 2, lineage="v1")
        revision_repo.find_version.return_value = old
        revision_repo.find_lineage_versions.return_value = [
            _v("v1", status=RevisionStatus.SUPERSEDED), old,
        ]
        outcome = await _run(
            uc,
            RevisionUploadOptions(
                supersedes_document_id="v2", version_label="2026-11 개정",
                effective_date=date(2026, 12, 1), revision_check_id="chk",
            ),
        )
        req = unified.execute.call_args.args[0]
        assert (req.lineage_id, req.version_no) == ("v1", 3)
        assert (req.version_label, req.effective_date) == ("2026-11 개정", date(2026, 12, 1))
        revision_repo.find_lineage_versions.assert_awaited_once_with("v1", "r")
        supersede.supersede.assert_awaited_once_with(
            old, "new", "col", revised_by="7", request_id="r"
        )
        rev = outcome.revision
        assert (rev.applied, rev.lineage_id, rev.version_no) == (True, "v1", 3)
        assert (rev.superseded_document_id, rev.sync_state) == ("v2", "synced")
        check_log.record_decision.assert_awaited_once_with(
            "chk", decision=CheckDecision.REVISION, target_document_id="v2",
            decided_document_id="new", decided_by="7", request_id="r",
        )

    async def test_invalid_target_blocks_before_ingest(self, deps) -> None:
        uc, unified, revision_repo, _, _ = deps
        revision_repo.find_version.return_value = _v("x", kb="kb-other")
        revision_repo.find_lineage_versions.return_value = []
        with pytest.raises(RevisionTargetInvalidError) as e:
            await _run(uc, RevisionUploadOptions(supersedes_document_id="x"))
        assert e.value.reason == "other_kb"
        unified.execute.assert_not_awaited()

    async def test_missing_target(self, deps) -> None:
        uc, _, revision_repo, _, _ = deps
        revision_repo.find_version.return_value = None
        with pytest.raises(RevisionTargetInvalidError) as e:
            await _run(uc, RevisionUploadOptions(supersedes_document_id="x"))
        assert e.value.reason == "not_found"

    @pytest.mark.parametrize("status", ["partial", "failed"])
    async def test_incomplete_ingest_detaches_and_skips_supersede(self, deps, status) -> None:
        uc, unified, revision_repo, supersede, _ = deps
        unified.execute.return_value = _result(status)
        old = _v("v1")
        revision_repo.find_version.return_value = old
        revision_repo.find_lineage_versions.return_value = [old]
        outcome = await _run(uc, RevisionUploadOptions(supersedes_document_id="v1"))
        supersede.supersede.assert_not_awaited()
        revision_repo.assign_lineage.assert_awaited_once_with(
            "new", lineage_id=None, version_no=1, request_id="r"
        )
        assert outcome.revision.applied is False
        assert outcome.revision.reason == "ingest_incomplete"

    async def test_pending_sync_is_reported(self, deps) -> None:
        uc, _, revision_repo, supersede, _ = deps
        old = _v("v1")
        revision_repo.find_version.return_value = old
        revision_repo.find_lineage_versions.return_value = [old]
        supersede.supersede.return_value = SyncState.PENDING
        outcome = await _run(uc, RevisionUploadOptions(supersedes_document_id="v1"))
        assert outcome.revision.applied is True
        assert outcome.revision.sync_state == "pending"

    async def test_new_document_decision_recorded(self, deps) -> None:
        uc, _, _, _, check_log = deps
        await _run(uc, RevisionUploadOptions(revision_check_id="chk"))
        check_log.record_decision.assert_awaited_once_with(
            "chk", decision=CheckDecision.NEW, target_document_id=None,
            decided_document_id="new", decided_by="7", request_id="r",
        )

    async def test_check_log_failure_does_not_fail_upload(self, deps) -> None:
        uc, _, _, _, check_log = deps
        check_log.record_decision.side_effect = RuntimeError("db")
        outcome = await _run(uc, RevisionUploadOptions(revision_check_id="chk"))
        assert outcome.result.document_id == "new"


class TestWithoutRevisionDeps:
    async def test_revision_request_without_repo_is_rejected(self) -> None:
        kb_repo = AsyncMock()
        kb_repo.find_by_id.return_value = _kb()
        dept = AsyncMock()
        dept.find_departments_by_user.return_value = []
        uc = KnowledgeBaseUploadUseCase(
            kb_repo=kb_repo, policy=KnowledgeBasePolicy(), dept_repo=dept,
            unified_upload=AsyncMock(), logger=MagicMock(),
        )
        with pytest.raises(RevisionTargetInvalidError):
            await _run(uc, RevisionUploadOptions(supersedes_document_id="x"))
