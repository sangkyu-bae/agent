"""KB 업로드 엔드포인트 개정 필드·409·revision 응답 — document-revision Design §4.2 #2, §6.1."""
from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.knowledge_base_router import get_kb_upload_use_case, router
from src.application.document_revision.schemas import (
    KbUploadOutcome,
    RevisionApplyResult,
    RevisionUploadOptions,
)
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
    DocumentVersion,
    RevisionStatus,
    SyncState,
)
from src.domain.knowledge_base.entities import KnowledgeBase
from src.interfaces.dependencies.auth import get_current_user

KB_ID = "kb-1"
URL = f"/api/v1/knowledge-bases/{KB_ID}/documents"
FILES = {"file": ("규정_v3.pdf", b"%PDF-1.4", "application/pdf")}


def _kb() -> KnowledgeBase:
    return KnowledgeBase(
        id=KB_ID, name="규정", owner_id=1, scope=CollectionScope.PERSONAL,
        collection_name="col",
    )


def _outcome(revision: RevisionApplyResult) -> KbUploadOutcome:
    return KbUploadOutcome(
        result=UnifiedUploadResult(
            document_id="new", filename="규정_v3.pdf", total_pages=1, chunk_count=2,
            collection_name="col",
            qdrant=QdrantStoreResult(stored_ids=["a"], embedding_model="m"),
            es=EsStoreResult(indexed_count=2), chunking_config={}, status="completed",
        ),
        kb=_kb(), summary_launch=None, revision=revision,
    )


@pytest.fixture
def uc() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client(uc) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_kb_upload_use_case] = lambda: uc
    app.dependency_overrides[get_current_user] = lambda: User(
        id=1, email="a@b.c", password_hash="h", role=UserRole.USER,
        status=UserStatus.APPROVED,
    )
    return TestClient(app)


def test_form_fields_are_passed_as_revision_options(client, uc) -> None:
    uc.execute_with_revision.return_value = _outcome(
        RevisionApplyResult(
            applied=True, lineage_id="v1", version_no=3,
            superseded_document_id="v2", sync_state="synced",
        )
    )
    resp = client.post(
        URL, files=FILES,
        data={
            "supersedes_document_id": "v2",
            "version_label": "2026-11 개정",
            "effective_date": "2026-12-01",
            "revision_check_id": "chk",
        },
    )
    assert resp.status_code == 200
    options = uc.execute_with_revision.call_args.kwargs["revision"]
    assert options == RevisionUploadOptions(
        supersedes_document_id="v2", version_label="2026-11 개정",
        effective_date=date(2026, 12, 1), revision_check_id="chk",
    )
    assert resp.json()["revision"] == {
        "applied": True, "lineage_id": "v1", "version_no": 3,
        "superseded_document_id": "v2", "sync_state": "synced", "reason": None,
    }


def test_no_form_fields_means_empty_options(client, uc) -> None:
    uc.execute_with_revision.return_value = _outcome(
        RevisionApplyResult(
            applied=False, lineage_id=None, version_no=1,
            superseded_document_id=None, sync_state=None,
        )
    )
    resp = client.post(URL, files=FILES)
    assert resp.status_code == 200
    assert uc.execute_with_revision.call_args.kwargs["revision"] == RevisionUploadOptions()
    assert resp.json()["revision"]["applied"] is False


def test_invalid_effective_date_is_422(client, uc) -> None:
    resp = client.post(URL, files=FILES, data={"effective_date": "2026-13-45"})
    assert resp.status_code == 422
    uc.execute_with_revision.assert_not_awaited()


def test_too_long_label_is_422(client, uc) -> None:
    resp = client.post(URL, files=FILES, data={"version_label": "x" * 101})
    assert resp.status_code == 422


def test_duplicate_is_409_with_existing_document(client, uc) -> None:
    existing = DocumentVersion(
        document_id="old", kb_id=KB_ID, filename="규정.pdf", lineage_id=None,
        version_no=2, version_label="2025 개정", effective_date=None,
        revision_status=RevisionStatus.ACTIVE, sync_state=SyncState.SYNCED,
        file_hash="h", superseded_by=None, superseded_at=None, revised_by=None,
        created_at=datetime(2026, 3, 2, 9, 0),
    )
    uc.execute_with_revision.side_effect = DuplicateDocumentError(existing)
    resp = client.post(URL, files=FILES)
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "DUPLICATE_DOCUMENT"
    assert detail["document"]["document_id"] == "old"
    assert detail["document"]["filename"] == "규정.pdf"
    assert detail["document"]["version_no"] == 2
    assert detail["document"]["revision_status"] == "active"


def test_invalid_target_is_409_with_reason(client, uc) -> None:
    uc.execute_with_revision.side_effect = RevisionTargetInvalidError("other_kb")
    resp = client.post(URL, files=FILES, data={"supersedes_document_id": "x"})
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail == {
        "code": "REVISION_TARGET_INVALID", "reason": "other_kb", "message": "other_kb",
    }
