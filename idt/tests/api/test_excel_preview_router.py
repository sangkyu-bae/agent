"""/files/{file_id}/preview 라우터 테스트 (excel-preview Design §4.2, §8.2 #8~10).

기존 test_document_extractor_router.py는 무수정 유지(additive) — 프리뷰 전용 파일.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.document_extractor_router import (
    get_excel_preview_use_case,
    router,
)
from src.application.excel_preview.schemas import (
    ExcelPreviewResponse,
    ExcelPreviewSheet,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.excel_preview.exceptions import (
    PreviewFileNotFoundError,
    PreviewForbiddenError,
    PreviewParseFailedError,
    PreviewUnsupportedError,
)
from src.interfaces.dependencies.auth import get_current_user

FILE_ID = "e" * 32


def _user(uid: int = 7) -> User:
    return User(
        email="t@t.com", password_hash="h",
        role=UserRole.USER, status=UserStatus.APPROVED, id=uid,
    )


def _make_app(use_case=None, with_auth: bool = True) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    if with_auth:
        app.dependency_overrides[get_current_user] = lambda: _user()
    if use_case is not None:
        app.dependency_overrides[get_excel_preview_use_case] = lambda: use_case
    return app


def _response() -> ExcelPreviewResponse:
    return ExcelPreviewResponse(
        file_id=FILE_ID,
        filename="매출현황.xlsx",
        max_rows=100,
        max_cols=50,
        sheets=[
            ExcelPreviewSheet(
                name="Sheet1", columns=["지점", "매출"],
                rows=[["서울", "1200"]], total_rows=20001, total_cols=2,
                truncated=True,
            )
        ],
    )


class TestPreviewRoute:
    def test_success_200_full_schema(self):
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=_response())
        client = TestClient(_make_app(uc))

        res = client.get(f"/api/v1/document-extractor/files/{FILE_ID}/preview")

        assert res.status_code == 200
        body = res.json()
        assert body["file_id"] == FILE_ID
        assert body["filename"] == "매출현황.xlsx"
        assert body["max_rows"] == 100
        assert body["max_cols"] == 50
        sheet = body["sheets"][0]
        assert sheet["name"] == "Sheet1"
        assert sheet["columns"] == ["지점", "매출"]
        assert sheet["rows"] == [["서울", "1200"]]
        assert sheet["total_rows"] == 20001
        assert sheet["total_cols"] == 2
        assert sheet["truncated"] is True
        # owner는 토큰 user.id에서 (위변조 방지, 다운로드와 동일 계약)
        assert uc.execute.call_args.kwargs["owner_user_id"] == "7"
        assert uc.execute.call_args.kwargs["file_id"] == FILE_ID

    def test_unauthenticated_401(self):
        client = TestClient(_make_app(with_auth=False))
        res = client.get(f"/api/v1/document-extractor/files/{FILE_ID}/preview")
        assert res.status_code == 401

    @pytest.mark.parametrize(
        "error,status,code",
        [
            (PreviewFileNotFoundError("gone"), 404, "FILE_NOT_FOUND"),
            (PreviewForbiddenError("not yours"), 403, "FORBIDDEN"),
            (PreviewUnsupportedError("docx"), 415, "PREVIEW_UNSUPPORTED"),
            (PreviewParseFailedError("corrupt"), 422, "PREVIEW_PARSE_FAILED"),
        ],
    )
    def test_error_contract(self, error, status, code):
        uc = MagicMock()
        uc.execute = AsyncMock(side_effect=error)
        client = TestClient(_make_app(uc))

        res = client.get(f"/api/v1/document-extractor/files/{FILE_ID}/preview")

        assert res.status_code == status
        assert res.json()["detail"]["code"] == code
