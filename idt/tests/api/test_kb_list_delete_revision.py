"""KB 문서 목록·삭제 개정 확장 — document-revision Design §4.2 #3·#9."""
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.knowledge_base_router import (
    get_delete_kb_document_use_case,
    get_list_kb_documents_use_case,
    router,
)
from src.application.knowledge_base.list_documents_use_case import (
    KbDocumentItem,
    KbDocumentListResult,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.doc_browse.schemas import DeleteDocumentResult
from src.domain.document_revision.value_objects import (
    DocumentVersion,
    RevisionStatus,
    SyncState,
)
from src.interfaces.dependencies.auth import get_current_user


@pytest.fixture
def list_uc() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def delete_uc() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client(list_uc, delete_uc) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_list_kb_documents_use_case] = lambda: list_uc
    app.dependency_overrides[get_delete_kb_document_use_case] = lambda: delete_uc
    app.dependency_overrides[get_current_user] = lambda: User(
        id=7, email="a@b.c", password_hash="h", role=UserRole.USER,
        status=UserStatus.APPROVED,
    )
    return TestClient(app)


def test_list_includes_version_fields_and_pending_sync(client, list_uc) -> None:
    list_uc.execute.return_value = KbDocumentListResult(
        kb_id="kb-1", kb_name="k",
        documents=[KbDocumentItem(
            document_id="v2", filename="규정.pdf", chunk_count=3, chunk_strategy="x",
            created_at=datetime(2026, 11, 1), can_delete=True, version_no=2,
            version_label="2026-11 개정", lineage_id="v1", has_history=True,
        )],
        total=1, offset=0, limit=20,
        pending_sync=[DocumentVersion(
            document_id="v1", kb_id="kb-1", filename="규정_old.pdf", lineage_id=None,
            version_no=1, version_label=None, effective_date=None,
            revision_status=RevisionStatus.SUPERSEDED, sync_state=SyncState.PENDING,
            file_hash=None, superseded_by="v2", superseded_at=None, revised_by=None,
            created_at=None,
        )],
    )
    body = client.get("/api/v1/knowledge-bases/kb-1/documents").json()
    doc = body["documents"][0]
    assert (doc["version_no"], doc["version_label"], doc["lineage_id"]) == (
        2, "2026-11 개정", "v1",
    )
    assert doc["has_history"] is True and doc["revision_status"] == "active"
    assert doc["sync_state"] == "synced" and doc["effective_date"] is None
    assert body["pending_sync"][0]["document_id"] == "v1"
    assert body["pending_sync"][0]["sync_state"] == "pending"


def _deleted(restored=None) -> DeleteDocumentResult:
    return DeleteDocumentResult(
        document_id="v2", collection_name="c", filename="v2.pdf",
        deleted_qdrant_chunks=1, deleted_es_chunks=1, status="deleted",
        restored_document_id=restored,
    )


def test_delete_restores_previous_by_default(client, delete_uc) -> None:
    delete_uc.execute.return_value = _deleted("v1")
    resp = client.delete("/api/v1/knowledge-bases/kb-1/documents/v2")
    assert resp.status_code == 200
    assert delete_uc.execute.call_args.kwargs["restore_previous"] is True
    assert resp.json()["restored_document_id"] == "v1"


def test_delete_can_skip_restore(client, delete_uc) -> None:
    delete_uc.execute.return_value = _deleted()
    resp = client.delete(
        "/api/v1/knowledge-bases/kb-1/documents/v2?restore_previous=false"
    )
    assert delete_uc.execute.call_args.kwargs["restore_previous"] is False
    assert resp.json()["restored_document_id"] is None


def test_delete_restore_pending_is_409(client, delete_uc) -> None:
    """Act-1 (Gap I2): 이전 버전 복귀 표식이 끝나지 않아 삭제를 멈추면 409."""
    from src.domain.document_revision.errors import RestorePendingError

    delete_uc.execute.side_effect = RestorePendingError("restore_pending")
    resp = client.delete("/api/v1/knowledge-bases/kb-1/documents/v2")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "RESTORE_PENDING"
