"""POST /api/v1/agent/attachments 통합 테스트 (Design §8.2)."""
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.agent_attachment_router import (
    router,
    get_upload_attachment_use_case,
)
from src.domain.agent_attachment.exceptions import (
    AttachmentTooLargeError,
    InvalidAttachmentError,
)
from src.domain.agent_attachment.value_objects import (
    AttachmentType,
    StoredAttachment,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.interfaces.dependencies.auth import get_current_user


def _user(uid: int = 7) -> User:
    return User(
        email="t@t.com", password_hash="h",
        role=UserRole.USER, status=UserStatus.APPROVED, id=uid,
    )


def _make_app(use_case) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _user()
    app.dependency_overrides[get_upload_attachment_use_case] = lambda: use_case
    return app


def _ok_uc() -> MagicMock:
    uc = MagicMock()
    uc.execute.return_value = StoredAttachment(
        file_id="a" * 32, type=AttachmentType.EXCEL,
        filename="sales.xlsx", size=11, owner_user_id="7",
        file_path="/tmp/a.xlsx",
    )
    return uc


class TestUploadHappy:
    def test_returns_201_with_file_id(self) -> None:
        client = TestClient(_make_app(_ok_uc()))
        files = {"file": ("sales.xlsx", b"hello-excel", "application/vnd.ms-excel")}
        res = client.post("/api/v1/agent/attachments", files=files)
        assert res.status_code == 201
        body = res.json()
        assert body["file_id"] == "a" * 32
        assert body["type"] == "excel"
        assert body["filename"] == "sales.xlsx"

    def test_passes_authenticated_user_as_owner(self) -> None:
        uc = _ok_uc()
        client = TestClient(_make_app(uc))
        files = {"file": ("a.xlsx", b"bytes", "application/vnd.ms-excel")}
        client.post("/api/v1/agent/attachments", files=files)
        kwargs = uc.execute.call_args.kwargs
        assert kwargs["owner_user_id"] == "7"  # Form이 아닌 토큰 user.id
        assert kwargs["file_bytes"] == b"bytes"
        assert kwargs["filename"] == "a.xlsx"


class TestUploadErrors:
    def test_requires_file(self) -> None:
        client = TestClient(_make_app(_ok_uc()))
        assert client.post("/api/v1/agent/attachments").status_code == 422

    def test_invalid_attachment_returns_400(self) -> None:
        uc = MagicMock()
        uc.execute.side_effect = InvalidAttachmentError("지원하지 않는 형식")
        client = TestClient(_make_app(uc))
        files = {"file": ("a.csv", b"x", "text/csv")}
        res = client.post("/api/v1/agent/attachments", files=files)
        assert res.status_code == 400
        assert res.json()["detail"]["code"] == "INVALID_ATTACHMENT"

    def test_too_large_returns_413(self) -> None:
        uc = MagicMock()
        uc.execute.side_effect = AttachmentTooLargeError("too big")
        client = TestClient(_make_app(uc))
        files = {"file": ("a.xlsx", b"x", "application/vnd.ms-excel")}
        res = client.post("/api/v1/agent/attachments", files=files)
        assert res.status_code == 413
        assert res.json()["detail"]["code"] == "ATTACHMENT_TOO_LARGE"
