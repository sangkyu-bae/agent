"""source-passage-viewer module-4 — 원본 라우트 HTTP 계약 (Design §4.2, §8.2 #13)."""
from unittest.mock import AsyncMock
from urllib.parse import quote

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.source_viewer_router import get_original_use_case, router
from src.application.source_viewer.get_original import OriginalFile
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.source_viewer.exceptions import (
    OriginalNotAvailableError,
    UnsupportedOriginalError,
)
from src.interfaces.dependencies.auth import get_current_user

_DOC = "8f1c2d3e-0000-4000-8000-000000000001"
_URL = f"/api/v1/source-viewer/kb/kb-1/documents/{_DOC}/original"


def _client(use_case, *, authed=True) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_original_use_case] = lambda: use_case
    if authed:
        app.dependency_overrides[get_current_user] = lambda: User(
            id=1, email="a@b.c", password_hash="h",
            role=UserRole.USER, status=UserStatus.APPROVED,
        )
    return TestClient(app)


def _uc(result=None, error=None):
    uc = AsyncMock()
    uc.execute.side_effect = error
    uc.execute.return_value = result
    return uc


def test_returns_inline_pdf_with_safe_headers():
    uc = _uc(OriginalFile(content=b"%PDF-1.4", media_type="application/pdf", filename="여신 규정.pdf"))
    res = _client(uc).get(_URL)
    assert res.status_code == 200
    assert res.content == b"%PDF-1.4"
    assert res.headers["content-type"] == "application/pdf"
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["cache-control"] == "private, max-age=300"
    disposition = res.headers["content-disposition"]
    assert disposition.startswith("inline;")
    assert f"filename*=UTF-8''{quote('여신 규정.pdf')}" in disposition


def test_unauthenticated_is_rejected():
    res = _client(_uc(), authed=False).get(_URL)
    assert res.status_code in (401, 403)


@pytest.mark.parametrize(
    "error, status",
    [
        (PermissionError("No read access"), 403),
        (ValueError("Document 'x' not found in knowledge base 'kb-1'"), 404),
        (ValueError("Knowledge base 'kb-1' not found"), 404),
        (OriginalNotAvailableError(), 404),
        (UnsupportedOriginalError(), 415),
    ],
)
def test_error_mapping(error, status):
    res = _client(_uc(error=error)).get(_URL)
    assert res.status_code == status


def test_not_available_has_code():
    res = _client(_uc(error=OriginalNotAvailableError())).get(_URL)
    assert res.json()["detail"] == "ORIGINAL_NOT_AVAILABLE"
