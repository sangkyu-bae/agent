"""POST /api/v1/knowledge-bases/quick L1 — Design §8.2 #9~#13."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.routes.knowledge_base_router import (
    get_kb_quick_create_use_case,
    router,
)
from src.application.knowledge_base.quick_create_use_case import (
    QuickCreateResult,
    QuickDocumentResult,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.kb_default_setting.errors import KbDefaultsNotConfiguredError
from src.domain.knowledge_base.entities import KnowledgeBase
from src.interfaces.dependencies.auth import get_current_user

KB_ID = "3f1a9c2e-aaaa-bbbb-cccc-dddddddddddd"


def _kb() -> KnowledgeBase:
    return KnowledgeBase(
        id=KB_ID,
        name="여신 상담봇 지식",
        owner_id=1,
        scope=CollectionScope.PERSONAL,
        collection_name="kb-3f1a9c2e",
    )


def _result(docs: list[QuickDocumentResult]) -> QuickCreateResult:
    uploaded = sum(1 for d in docs if d.status == "uploaded")
    return QuickCreateResult(
        kb=_kb(),
        documents=tuple(docs),
        uploaded_count=uploaded,
        failed_count=len(docs) - uploaded,
    )


@pytest.fixture
def use_case() -> AsyncMock:
    uc = AsyncMock()
    uc.execute.return_value = _result(
        [
            QuickDocumentResult("a.pdf", "uploaded", "doc-a", 12, None),
            QuickDocumentResult("b.pdf", "failed", None, 0, "암호화된 문서입니다"),
        ]
    )
    return uc


@pytest.fixture
def client(use_case: AsyncMock) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_kb_quick_create_use_case] = lambda: use_case
    app.dependency_overrides[get_current_user] = lambda: User(
        id=1, email="u@test.com", password_hash="h",
        role=UserRole.USER, status=UserStatus.APPROVED,
    )
    return TestClient(app)


def _post(client: TestClient, files: int = 2, **data):
    body = {"name": "여신 상담봇 지식", "scope": "PERSONAL", **data}
    return client.post(
        "/api/v1/knowledge-bases/quick",
        data=body,
        files=[
            ("files", (f"f{i}.pdf", b"%PDF-1.4", "application/pdf"))
            for i in range(files)
        ],
    )


class TestQuickCreate:
    def test_returns_201_with_per_file_status(self, client, use_case):
        resp = _post(client)
        assert resp.status_code == 201
        body = resp.json()
        assert body["kb_id"] == KB_ID
        assert body["collection_name"] == "kb-3f1a9c2e"
        assert body["scope"] == "PERSONAL"
        assert body["uploaded_count"] == 1 and body["failed_count"] == 1
        assert body["documents"][0] == {
            "filename": "a.pdf", "status": "uploaded",
            "document_id": "doc-a", "chunk_count": 12, "error": None,
        }
        assert body["documents"][1]["status"] == "failed"
        assert body["documents"][1]["error"] == "암호화된 문서입니다"

    def test_passes_files_in_order_with_bytes(self, client, use_case):
        _post(client, files=2)
        kwargs = use_case.execute.await_args.kwargs
        assert [f.filename for f in kwargs["files"]] == ["f0.pdf", "f1.pdf"]
        assert kwargs["files"][0].content == b"%PDF-1.4"
        assert kwargs["scope"] == CollectionScope.PERSONAL
        assert kwargs["name"] == "여신 상담봇 지식"

    def test_department_id_forwarded(self, client, use_case):
        _post(client, scope="DEPARTMENT", department_id="d1")
        kwargs = use_case.execute.await_args.kwargs
        assert kwargs["scope"] == CollectionScope.DEPARTMENT
        assert kwargs["department_id"] == "d1"

    def test_invalid_scope_422(self, client):
        assert _post(client, scope="FRIENDS").status_code == 422

    def test_no_files_422(self, client):
        resp = client.post(
            "/api/v1/knowledge-bases/quick",
            data={"name": "x", "scope": "PERSONAL"},
        )
        assert resp.status_code == 422

    def test_not_configured_422_with_code(self, client, use_case):
        use_case.execute.side_effect = KbDefaultsNotConfiguredError()
        resp = _post(client)
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "KB_DEFAULTS_NOT_CONFIGURED"

    def test_permission_error_403(self, client, use_case):
        use_case.execute.side_effect = PermissionError("No department membership")
        assert _post(client).status_code == 403

    def test_collection_conflict_409(self, client, use_case):
        use_case.execute.side_effect = ValueError(
            "Collection 'kb-3f1a9c2e' already exists"
        )
        assert _post(client).status_code == 409

    def test_validation_value_error_422(self, client, use_case):
        use_case.execute.side_effect = ValueError("Unsupported file extension: .exe")
        assert _post(client).status_code == 422
