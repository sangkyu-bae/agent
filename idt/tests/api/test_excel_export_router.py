"""API tests for Excel export router."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.excel_export_router import get_excel_export_use_case, router
from src.domain.excel_export.schemas import ExcelExportResult, ExcelSheetData


@pytest.fixture
def mock_use_case():
    use_case = MagicMock()
    use_case.export = AsyncMock(
        return_value=ExcelExportResult(
            filename="report.xlsx",
            user_id="user-1",
            request_id="req-001",
            excel_bytes=b"PK fake excel",
            size_bytes=13,
            sheet_count=1,
            exporter_used="pandas+openpyxl",
        )
    )
    return use_case


@pytest.fixture
def client(mock_use_case):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_excel_export_use_case] = lambda: mock_use_case
    return TestClient(app)


class TestExcelExportRouter:
    def test_export_returns_200_with_xlsx_bytes(self, client):
        response = client.post(
            "/api/v1/excel/export",
            json={
                "filename": "report.xlsx",
                "user_id": "user-1",
                "sheets": [
                    {
                        "sheet_name": "Data",
                        "columns": ["A", "B"],
                        "rows": [[1, 2]],
                    }
                ],
            },
        )
        assert response.status_code == 200
        assert "spreadsheet" in response.headers["content-type"]

    def test_export_sets_content_disposition(self, client):
        response = client.post(
            "/api/v1/excel/export",
            json={
                "filename": "report.xlsx",
                "user_id": "user-1",
                "sheets": [{"columns": ["A"], "rows": []}],
            },
        )
        assert "report.xlsx" in response.headers["content-disposition"]

    def test_export_returns_excel_bytes_as_body(self, client):
        response = client.post(
            "/api/v1/excel/export",
            json={
                "filename": "report.xlsx",
                "user_id": "user-1",
                "sheets": [{"columns": ["A"], "rows": []}],
            },
        )
        assert response.content == b"PK fake excel"

    def test_export_missing_sheets_returns_422(self, client):
        response = client.post(
            "/api/v1/excel/export",
            json={"filename": "report.xlsx", "user_id": "user-1"},
        )
        assert response.status_code == 422

    def test_export_missing_user_id_returns_422(self, client):
        response = client.post(
            "/api/v1/excel/export",
            json={
                "filename": "report.xlsx",
                "sheets": [{"columns": ["A"], "rows": []}],
            },
        )
        assert response.status_code == 422
