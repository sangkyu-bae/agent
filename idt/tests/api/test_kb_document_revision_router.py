"""POST /knowledge-bases/{kb_id}/documents/revision-check — Design §4.2 #1."""
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.kb_document_revision_router import (
    get_revision_check_use_case,
    router,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.document_revision.value_objects import (
    CheckVerdict,
    DocumentVersion,
    LlmStatus,
    LlmVerdict,
    RevisionCandidate,
    RevisionCheckResult,
    RevisionStatus,
    SyncState,
)
from src.interfaces.dependencies.auth import get_current_user

URL = "/api/v1/knowledge-bases/kb-1/documents/revision-check"
FILES = {"file": ("규정_2026.pdf", b"%PDF", "application/pdf")}


@pytest.fixture
def uc() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client(uc) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_revision_check_use_case] = lambda: uc
    app.dependency_overrides[get_current_user] = lambda: User(
        id=7, email="a@b.c", password_hash="h", role=UserRole.USER,
        status=UserStatus.APPROVED,
    )
    return TestClient(app)


def test_candidate_response_shape(client, uc) -> None:
    uc.execute.return_value = RevisionCheckResult(
        check_id="chk", verdict=CheckVerdict.REVISION_CANDIDATE, duplicate_of=None,
        candidates=[RevisionCandidate(
            document_id="old", filename="규정_2025.pdf", version_no=2,
            version_label="2025-03 개정", filename_score=0.92, content_score=0.88,
            combined_score=0.896, llm_verdict=LlmVerdict.SAME, llm_reason="같은 규정",
        )],
        suggested_document_id="old", llm_status=LlmStatus.OK, elapsed_ms=4210,
    )
    resp = client.post(URL, files=FILES)
    assert resp.status_code == 200
    body = resp.json()
    assert body["check_id"] == "chk"
    assert body["verdict"] == "revision_candidate"
    assert body["suggested_document_id"] == "old"
    assert body["llm_status"] == "ok" and body["elapsed_ms"] == 4210
    assert body["duplicate_of"] is None
    assert body["candidates"][0] == {
        "document_id": "old", "filename": "규정_2025.pdf", "version_no": 2,
        "version_label": "2025-03 개정", "filename_score": 0.92,
        "content_score": 0.88, "combined_score": 0.896,
        "llm_verdict": "same_document_revision", "llm_reason": "같은 규정",
    }
    args = uc.execute.call_args.args
    assert args[0] == "kb-1" and args[2] == b"%PDF" and args[3] == "규정_2026.pdf"


def test_duplicate_response_includes_document(client, uc) -> None:
    uc.execute.return_value = RevisionCheckResult(
        check_id="chk", verdict=CheckVerdict.DUPLICATE,
        duplicate_of=DocumentVersion(
            document_id="old", kb_id="kb-1", filename="규정.pdf", lineage_id=None,
            version_no=1, version_label=None, effective_date=None,
            revision_status=RevisionStatus.ACTIVE, sync_state=SyncState.SYNCED,
            file_hash="h", superseded_by=None, superseded_at=None, revised_by=None,
            created_at=datetime(2026, 3, 2),
        ),
        candidates=[], suggested_document_id=None, llm_status=LlmStatus.SKIPPED,
        elapsed_ms=5,
    )
    body = client.post(URL, files=FILES).json()
    assert body["verdict"] == "duplicate"
    assert body["duplicate_of"]["document_id"] == "old"
    assert body["duplicate_of"]["created_at"].startswith("2026-03-02")


def test_permission_error_is_403(client, uc) -> None:
    uc.execute.side_effect = PermissionError("no write")
    assert client.post(URL, files=FILES).status_code == 403


def test_kb_not_found_is_404(client, uc) -> None:
    uc.execute.side_effect = ValueError("Knowledge base 'kb-1' not found")
    assert client.post(URL, files=FILES).status_code == 404


# ── module-5: 이력·되돌리기·연결·메타·재반영·모드 ─────────────────
from datetime import date  # noqa: E402

from src.api.routes.kb_document_revision_router import (  # noqa: E402
    get_revision_management_use_case,
)
from src.api.routes.knowledge_base_router import (  # noqa: E402
    get_knowledge_base_use_case,
)
from src.application.document_revision.revision_management_use_case import (  # noqa: E402
    RollbackResult,
)
from src.domain.collection.permission_schemas import CollectionScope  # noqa: E402
from src.domain.document_revision.errors import (  # noqa: E402
    RevisionLinkInvalidError,
    RevisionModeNotAvailableError,
    RollbackNotAllowedError,
)
from src.domain.document_revision.value_objects import RollbackMode  # noqa: E402
from src.domain.knowledge_base.entities import KnowledgeBase  # noqa: E402

BASE = "/api/v1/knowledge-bases/kb-1/documents"


def _ver(doc, version=1, lineage=None, status=RevisionStatus.ACTIVE):
    return DocumentVersion(
        document_id=doc, kb_id="kb-1", filename=f"{doc}.pdf", lineage_id=lineage,
        version_no=version, version_label=None, effective_date=None,
        revision_status=status, sync_state=SyncState.SYNCED, file_hash=None,
        superseded_by=None, superseded_at=None, revised_by=None, created_at=None,
    )


@pytest.fixture
def mgmt() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def kb_uc() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client2(uc, mgmt, kb_uc) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_revision_check_use_case] = lambda: uc
    app.dependency_overrides[get_revision_management_use_case] = lambda: mgmt
    app.dependency_overrides[get_knowledge_base_use_case] = lambda: kb_uc
    app.dependency_overrides[get_current_user] = lambda: User(
        id=7, email="a@b.c", password_hash="h", role=UserRole.USER,
        status=UserStatus.APPROVED,
    )
    return TestClient(app)


def test_versions(client2, mgmt) -> None:
    mgmt.versions.return_value = [
        _ver("v2", 2, "v1"), _ver("v1", status=RevisionStatus.SUPERSEDED),
    ]
    body = client2.get(f"{BASE}/v2/versions").json()
    assert body["lineage_id"] == "v1"
    assert [v["version_no"] for v in body["versions"]] == [2, 1]
    assert body["versions"][1]["revision_status"] == "superseded"


def test_rollback(client2, mgmt) -> None:
    mgmt.rollback.return_value = RollbackResult(
        restored_document_id="v1", detached_document_id="v2",
        deleted_document_id=None, sync_state="synced",
    )
    resp = client2.post(f"{BASE}/v2/revision-rollback", json={"mode": "detach"})
    assert resp.status_code == 200
    assert resp.json() == {
        "restored_document_id": "v1", "detached_document_id": "v2",
        "deleted_document_id": None, "sync_state": "synced",
    }
    assert mgmt.rollback.call_args.args[2] is RollbackMode.DETACH


def test_rollback_invalid_mode_is_422(client2) -> None:
    assert client2.post(
        f"{BASE}/v2/revision-rollback", json={"mode": "nope"}
    ).status_code == 422


def test_rollback_not_allowed_is_409(client2, mgmt) -> None:
    mgmt.rollback.side_effect = RollbackNotAllowedError("first_version")
    resp = client2.post(f"{BASE}/v1/revision-rollback", json={"mode": "detach"})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "ROLLBACK_NOT_ALLOWED"


def test_link(client2, mgmt) -> None:
    mgmt.link.return_value = (_ver("n1", 3, "o1"), SyncState.PENDING)
    resp = client2.post(
        f"{BASE}/n1/revision-link", json={"supersedes_document_id": "o2"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["document"]["version_no"] == 3 and body["sync_state"] == "pending"
    assert mgmt.link.call_args.args[:3] == ("kb-1", "n1", "o2")


def test_link_invalid_is_409(client2, mgmt) -> None:
    mgmt.link.side_effect = RevisionLinkInvalidError("source_has_history")
    resp = client2.post(f"{BASE}/n1/revision-link", json={"supersedes_document_id": "o"})
    assert resp.status_code == 409
    assert resp.json()["detail"]["reason"] == "source_has_history"


def test_update_meta(client2, mgmt) -> None:
    mgmt.update_meta.return_value = _ver("v1")
    resp = client2.patch(
        f"{BASE}/v1/revision-meta",
        json={"version_label": "2026-11 개정", "effective_date": "2026-12-01"},
    )
    assert resp.status_code == 200
    args = mgmt.update_meta.call_args.args
    assert args[2:4] == ("2026-11 개정", date(2026, 12, 1))


def test_resync(client2, mgmt) -> None:
    mgmt.resync.return_value = _ver("v1", status=RevisionStatus.SUPERSEDED)
    body = client2.post(f"{BASE}/v1/revision-sync").json()
    assert body == {
        "document_id": "v1", "revision_status": "superseded", "sync_state": "synced",
    }


def test_revision_mode_auto_is_422(client2, kb_uc) -> None:
    kb_uc.update_revision_mode.side_effect = RevisionModeNotAvailableError(
        "auto_not_available"
    )
    resp = client2.patch(
        "/api/v1/knowledge-bases/kb-1/revision-mode", json={"revision_mode": "auto"}
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "REVISION_MODE_NOT_AVAILABLE"


def test_revision_mode_suggest(client2, kb_uc) -> None:
    kb_uc.update_revision_mode.return_value = KnowledgeBase(
        id="kb-1", name="k", owner_id=7, scope=CollectionScope.PERSONAL,
        collection_name="c", revision_mode="suggest",
    )
    resp = client2.patch(
        "/api/v1/knowledge-bases/kb-1/revision-mode", json={"revision_mode": "suggest"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"kb_id": "kb-1", "revision_mode": "suggest"}
