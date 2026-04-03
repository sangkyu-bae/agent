"""Tests for Excel upload API endpoint."""
import pytest
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from src.api.routes.excel_upload import router, get_excel_upload_use_case
from src.domain.pipeline.schemas.excel_upload_schema import ExcelUploadResponse


@pytest.fixture
def app():
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.fixture
def client(app):
    return TestClient(app)


def _make_success_response(**kwargs) -> ExcelUploadResponse:
    defaults = dict(
        document_id="doc-111",
        filename="data.xlsx",
        sheet_count=1,
        chunk_count=5,
        stored_ids=["s1", "s2"],
        status="completed",
        errors=[],
    )
    defaults.update(kwargs)
    return ExcelUploadResponse(**defaults)


class TestExcelUploadEndpoint:
    def test_endpoint_exists(self, app, client):
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = _make_success_response()
        app.dependency_overrides[get_excel_upload_use_case] = lambda: mock_uc

        response = client.post("/api/v1/excel/upload")
        assert response.status_code != 404

        app.dependency_overrides.clear()

    def test_requires_file(self, app, client):
        mock_uc = AsyncMock()
        app.dependency_overrides[get_excel_upload_use_case] = lambda: mock_uc

        response = client.post("/api/v1/excel/upload")
        assert response.status_code == 422

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_upload_success_returns_200(self, app):
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = _make_success_response()
        app.dependency_overrides[get_excel_upload_use_case] = lambda: mock_uc

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            files = {"file": ("data.xlsx", b"fake-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            response = await ac.post(
                "/api/v1/excel/upload",
                files=files,
                params={"user_id": "user-001"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == "doc-111"
        assert data["status"] == "completed"
        assert data["sheet_count"] == 1
        assert data["chunk_count"] == 5
        assert data["stored_ids"] == ["s1", "s2"]

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_upload_failed_returns_500(self, app):
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = _make_success_response(
            document_id="",
            sheet_count=0,
            chunk_count=0,
            stored_ids=[],
            status="failed",
            errors=["Invalid Excel format"],
        )
        app.dependency_overrides[get_excel_upload_use_case] = lambda: mock_uc

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            files = {"file": ("bad.xlsx", b"not-excel", "application/octet-stream")}
            response = await ac.post(
                "/api/v1/excel/upload",
                files=files,
                params={"user_id": "user-001"},
            )

        assert response.status_code == 500
        data = response.json()
        assert "errors" in data["detail"]

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_upload_calls_use_case_with_correct_params(self, app):
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = _make_success_response()
        app.dependency_overrides[get_excel_upload_use_case] = lambda: mock_uc

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            file_content = b"some-bytes"
            files = {"file": ("report.xlsx", file_content, "application/vnd.ms-excel")}
            await ac.post(
                "/api/v1/excel/upload",
                files=files,
                params={"user_id": "user-xyz"},
            )

        call_kwargs = mock_uc.execute.call_args.kwargs
        assert call_kwargs["file_bytes"] == file_content
        assert call_kwargs["filename"] == "report.xlsx"
        assert call_kwargs["user_id"] == "user-xyz"
        assert "request_id" in call_kwargs

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_strategy_type_forwarded_to_use_case(self, app):
        """strategy_type query param is accepted (route does not error)."""
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = _make_success_response()
        app.dependency_overrides[get_excel_upload_use_case] = lambda: mock_uc

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            files = {"file": ("data.xlsx", b"bytes", "application/vnd.ms-excel")}
            response = await ac.post(
                "/api/v1/excel/upload",
                files=files,
                params={"user_id": "u1", "strategy_type": "parent_child"},
            )

        assert response.status_code == 200
        app.dependency_overrides.clear()
