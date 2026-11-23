"""RevisionManagementUseCase — 이력·되돌리기·사후 연결·메타·재반영 (Design §4.2 #4~#8)."""
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.document_revision.revision_management_use_case import (
    RevisionManagementUseCase,
)
from src.application.knowledge_base.content_browse_guard import KbDocumentContext
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.document_revision.errors import (
    RevisionLinkInvalidError,
    RollbackNotAllowedError,
)
from src.domain.document_revision.value_objects import (
    CheckDecision,
    CheckSource,
    DocumentVersion,
    RevisionStatus,
    RollbackMode,
    SyncState,
)
from src.domain.knowledge_base.entities import KnowledgeBase
from src.domain.knowledge_base.policy import KnowledgeBasePolicy

KB = "kb-1"


def _user(uid=7) -> User:
    return User(email="a@b.c", password_hash="h", role=UserRole.USER,
                status=UserStatus.APPROVED, id=uid)


def _kb() -> KnowledgeBase:
    return KnowledgeBase(id=KB, name="규정", owner_id=7,
                         scope=CollectionScope.PUBLIC, collection_name="col")


def _v(doc, version=1, lineage=None, status=RevisionStatus.ACTIVE, kb=KB):
    return DocumentVersion(
        document_id=doc, kb_id=kb, filename=f"{doc}.pdf", lineage_id=lineage,
        version_no=version, version_label=None, effective_date=None,
        revision_status=status, sync_state=SyncState.SYNCED, file_hash=None,
        superseded_by=None, superseded_at=None, revised_by=None, created_at=None,
    )


class _D:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.guard = AsyncMock()
        self.guard.ensure.side_effect = lambda kb_id, doc, user, rid: KbDocumentContext(
            kb_id=kb_id, document_id=doc, collection_name="col",
            filename=f"{doc}.pdf", chunk_strategy="x", kb=_kb(), uploader_id="7",
        )
        self.dept = AsyncMock()
        self.dept.find_departments_by_user.return_value = []
        self.repo = AsyncMock()
        self.supersede = AsyncMock()
        self.supersede.reactivate.side_effect = self._rec("reactivate", SyncState.SYNCED)
        self.supersede.supersede.side_effect = self._rec("supersede", SyncState.SYNCED)
        self.supersede.resync.return_value = SyncState.SYNCED
        self.repo.assign_lineage.side_effect = self._rec("assign_lineage")
        self.deleter = AsyncMock()
        self.deleter.check.side_effect = self._rec("delete_check", "ctx")
        self.deleter.delete_checked.side_effect = self._rec("delete")
        self.log = AsyncMock()

    def _rec(self, name, value=None):
        async def _f(*a, **k):
            self.calls.append(name)
            return value
        return _f

    def uc(self) -> RevisionManagementUseCase:
        return RevisionManagementUseCase(
            guard=self.guard, policy=KnowledgeBasePolicy(), dept_repo=self.dept,
            revision_repo=self.repo, supersede_service=self.supersede,
            kb_deleter=self.deleter, check_log_repo=self.log, logger=MagicMock(),
            id_factory=lambda: "log-1",
        )


@pytest.fixture
def d() -> _D:
    return _D()


class TestVersions:
    async def test_returns_lineage_newest_first(self, d) -> None:
        d.repo.find_version.return_value = _v("v2", 2, "v1")
        d.repo.find_lineage_versions.return_value = [
            _v("v1", status=RevisionStatus.SUPERSEDED), _v("v2", 2, "v1"),
        ]
        versions = await d.uc().versions(KB, "v2", _user(99), "r")  # 읽기 권한만 필요
        assert [v.document_id for v in versions] == ["v2", "v1"]
        d.repo.find_lineage_versions.assert_awaited_once_with("v1", "r")


class TestWritePermission:
    async def test_reader_without_write_is_rejected(self, d) -> None:
        d.repo.find_version.return_value = _v("v2", 2, "v1")
        with pytest.raises(PermissionError):
            await d.uc().update_meta(KB, "v2", "라벨", None, _user(99), "r")


class TestRollback:
    def _lineage(self, d):
        prev = _v("v1", status=RevisionStatus.SUPERSEDED)
        cur = _v("v2", 2, "v1")
        d.repo.find_version.return_value = cur
        d.repo.find_lineage_versions.return_value = [prev, cur]
        return prev, cur

    async def test_detach_reactivates_previous_first(self, d) -> None:
        self._lineage(d)
        result = await d.uc().rollback(KB, "v2", RollbackMode.DETACH, _user(), "r")
        assert d.calls == ["reactivate", "assign_lineage"]
        d.supersede.reactivate.assert_awaited_once_with("v1", "col", request_id="r")
        d.repo.assign_lineage.assert_awaited_once_with(
            "v2", lineage_id=None, version_no=1, request_id="r"
        )
        assert (result.restored_document_id, result.detached_document_id) == ("v1", "v2")
        assert result.deleted_document_id is None and result.sync_state == "synced"
        entry = d.log.save.call_args.args[0]
        assert entry.source is CheckSource.ROLLBACK
        assert entry.decision is CheckDecision.ROLLBACK_DETACH
        assert (entry.target_document_id, entry.decided_document_id) == ("v1", "v2")

    async def test_delete_checks_before_reactivating(self, d) -> None:
        self._lineage(d)
        result = await d.uc().rollback(KB, "v2", RollbackMode.DELETE, _user(), "r")
        assert d.calls == ["delete_check", "reactivate", "delete"]
        assert result.deleted_document_id == "v2"
        d.repo.assign_lineage.assert_not_awaited()

    async def test_delete_check_failure_keeps_everything(self, d) -> None:
        self._lineage(d)
        d.deleter.check.side_effect = PermissionError("no delete")
        with pytest.raises(PermissionError):
            await d.uc().rollback(KB, "v2", RollbackMode.DELETE, _user(), "r")
        d.supersede.reactivate.assert_not_awaited()

    async def test_first_version_not_allowed(self, d) -> None:
        d.repo.find_version.return_value = _v("v1")
        d.repo.find_lineage_versions.return_value = [_v("v1")]
        with pytest.raises(RollbackNotAllowedError):
            await d.uc().rollback(KB, "v1", RollbackMode.DETACH, _user(), "r")


class TestLink:
    async def test_link_joins_lineage_then_supersedes(self, d) -> None:
        new, old = _v("n1"), _v("o2", 2, "o1")
        d.repo.find_version.side_effect = lambda doc, rid: {"n1": new, "o2": old}[doc]
        d.repo.find_lineage_versions.side_effect = lambda lid, rid: {
            "n1": [new], "o1": [_v("o1", status=RevisionStatus.SUPERSEDED), old],
        }[lid]
        version, state = await d.uc().link(KB, "n1", "o2", _user(), "r")
        assert d.calls == ["assign_lineage", "supersede"]
        d.repo.assign_lineage.assert_awaited_once_with(
            "n1", lineage_id="o1", version_no=3, request_id="r"
        )
        d.supersede.supersede.assert_awaited_once_with(
            old, "n1", "col", revised_by="7", request_id="r"
        )
        assert state is SyncState.SYNCED
        entry = d.log.save.call_args.args[0]
        assert entry.source is CheckSource.MANUAL_LINK and entry.verdict == "manual"
        assert entry.decision is CheckDecision.REVISION

    async def test_link_target_in_other_kb(self, d) -> None:
        d.repo.find_version.side_effect = lambda doc, rid: {
            "n1": _v("n1"), "x": _v("x", kb="kb-2"),
        }[doc]
        d.repo.find_lineage_versions.side_effect = lambda lid, rid: [_v(lid)]
        with pytest.raises(RevisionLinkInvalidError) as e:
            await d.uc().link(KB, "n1", "x", _user(), "r")
        assert e.value.reason == "other_kb"
        d.supersede.supersede.assert_not_awaited()


class TestMetaAndSync:
    async def test_update_meta(self, d) -> None:
        d.repo.find_version.return_value = _v("v1")
        await d.uc().update_meta(KB, "v1", "2026-11 개정", date(2026, 12, 1), _user(), "r")
        d.repo.update_meta.assert_awaited_once_with(
            "v1", version_label="2026-11 개정", effective_date=date(2026, 12, 1),
            request_id="r",
        )

    async def test_resync(self, d) -> None:
        v = _v("v1", status=RevisionStatus.SUPERSEDED)
        d.repo.find_version.return_value = v
        await d.uc().resync(KB, "v1", _user(), "r")
        d.supersede.resync.assert_awaited_once_with(v, "col", request_id="r")


class TestRollbackRestorePending:
    """Act-1 (Gap I2): 이전 버전 재활성 표식이 끝나지 않으면 삭제하지 않고 분리로 낮춘다."""

    async def test_delete_falls_back_to_detach_when_restore_pending(self, d) -> None:
        TestRollback()._lineage(d)
        d.supersede.reactivate.side_effect = d._rec("reactivate", SyncState.PENDING)
        result = await d.uc().rollback(KB, "v2", RollbackMode.DELETE, _user(), "r")
        assert "delete" not in d.calls
        assert d.calls == ["delete_check", "reactivate", "assign_lineage"]
        assert result.deleted_document_id is None
        assert result.detached_document_id == "v2"
        assert result.sync_state == "pending"

    async def test_detach_clears_version_label(self, d) -> None:
        """Gap M5: 떼어낸 독립 v1 에 이전 계보의 라벨·시행일을 남기지 않는다."""
        TestRollback()._lineage(d)
        await d.uc().rollback(KB, "v2", RollbackMode.DETACH, _user(), "r")
        d.repo.update_meta.assert_awaited_once_with(
            "v2", version_label=None, effective_date=None, request_id="r"
        )
