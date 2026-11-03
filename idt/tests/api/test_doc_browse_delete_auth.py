"""컬렉션 문서 삭제 인증 — kb-document-management Design §8.2 L1 #13~15.

신원과 역할은 토큰에서만 온다. 헤더 위조는 판정에 쓰이지 않아야 한다.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.doc_browse_router import (
    get_delete_document_use_case,
    router,
)
from src.application.doc_browse.delete_document_use_case import (
    DeleteDocumentUseCase,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.doc_browse.schemas import DeleteDocumentResult
from src.interfaces.dependencies.auth import get_current_user

SINGLE_URL = "/api/v1/collections/col/documents/doc-1"
BATCH_URL = "/api/v1/collections/col/documents"
FORGED_ADMIN = {"X-User-Id": "999", "X-User-Role": "admin"}


def _user(role: UserRole) -> User:
    return User(
        id=7,
        email="t@t.com",
        password_hash="h",
        role=role,
        status=UserStatus.APPROVED,
    )


@pytest.fixture
def use_case() -> MagicMock:
    uc = MagicMock()
    uc.DocumentNotFoundError = DeleteDocumentUseCase.DocumentNotFoundError
    uc.PermissionDeniedError = DeleteDocumentUseCase.PermissionDeniedError
    uc.execute_single = AsyncMock(
        return_value=DeleteDocumentResult(
            document_id="doc-1",
            collection_name="col",
            filename="a.pdf",
            deleted_qdrant_chunks=1,
            deleted_es_chunks=1,
            status="deleted",
        )
    )
    uc.execute_batch = AsyncMock(
        return_value={
            "total": 1,
            "success_count": 1,
            "failure_count": 0,
            "results": [],
        }
    )
    return uc


def _client(use_case: MagicMock, user: User | None) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_delete_document_use_case] = lambda: use_case
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


class TestUnauthenticated:
    def test_single_rejected_with_forged_headers(self, use_case):
        resp = _client(use_case, None).delete(
            SINGLE_URL, headers=FORGED_ADMIN
        )

        assert resp.status_code == 401
        use_case.execute_single.assert_not_awaited()

    def test_batch_rejected_with_forged_headers(self, use_case):
        resp = _client(use_case, None).request(
            "DELETE",
            BATCH_URL,
            headers=FORGED_ADMIN,
            json={"document_ids": ["doc-1"]},
        )

        assert resp.status_code == 401
        use_case.execute_batch.assert_not_awaited()


class TestForgedHeadersIgnored:
    def test_single_uses_token_identity(self, use_case):
        resp = _client(use_case, _user(UserRole.USER)).delete(
            SINGLE_URL, headers=FORGED_ADMIN
        )

        assert resp.status_code == 200
        use_case.execute_single.assert_awaited_once_with(
            collection_name="col",
            document_id="doc-1",
            user_id="7",
            user_role="user",
        )

    def test_batch_uses_token_identity(self, use_case):
        resp = _client(use_case, _user(UserRole.USER)).request(
            "DELETE",
            BATCH_URL,
            headers=FORGED_ADMIN,
            json={"document_ids": ["doc-1"]},
        )

        assert resp.status_code == 200
        use_case.execute_batch.assert_awaited_once_with(
            collection_name="col",
            document_ids=["doc-1"],
            user_id="7",
            user_role="user",
        )


class TestAdminRole:
    def test_single_passes_admin_role(self, use_case):
        _client(use_case, _user(UserRole.ADMIN)).delete(SINGLE_URL)

        kwargs = use_case.execute_single.await_args.kwargs
        assert kwargs["user_role"] == "admin"

    def test_batch_passes_admin_role(self, use_case):
        _client(use_case, _user(UserRole.ADMIN)).request(
            "DELETE", BATCH_URL, json={"document_ids": ["doc-1"]}
        )

        kwargs = use_case.execute_batch.await_args.kwargs
        assert kwargs["user_role"] == "admin"


class TestExistingErrorsKept:
    def test_not_found(self, use_case):
        use_case.execute_single.side_effect = (
            DeleteDocumentUseCase.DocumentNotFoundError("missing")
        )
        resp = _client(use_case, _user(UserRole.USER)).delete(SINGLE_URL)
        assert resp.status_code == 404

    def test_permission_denied(self, use_case):
        use_case.execute_single.side_effect = (
            DeleteDocumentUseCase.PermissionDeniedError("denied")
        )
        resp = _client(use_case, _user(UserRole.USER)).delete(SINGLE_URL)
        assert resp.status_code == 403
