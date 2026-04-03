"""API tests for PDF export router.

POST /api/v1/pdf/export — HTML → PDF 변환 엔드포인트
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.pdf_export_router import get_html_to_pdf_use_case, router
from src.domain.pdf_export.schemas import HtmlToPdfResult


@pytest.fixture
def mock_use_case():
    use_case = MagicMock()
    use_case.convert = AsyncMock(
        return_value=HtmlToPdfResult(
            filename="report.pdf",
            user_id="user-1",
            request_id="req-001",
            pdf_bytes=b"%PDF-1.4 fake content",
            size_bytes=21,
            converter_used="xhtml2pdf",
        )
    )
    return use_case


@pytest.fixture
def client(mock_use_case):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_html_to_pdf_use_case] = lambda: mock_use_case
    return TestClient(app)


class TestPdfExportRouter:
    def test_export_returns_200_with_pdf_bytes(self, client):
        response = client.post(
            "/api/v1/pdf/export",
            json={
                "html_content": "<h1>Report</h1>",
                "filename": "report.pdf",
                "user_id": "user-1",
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"

    def test_export_sets_correct_content_disposition(self, client):
        response = client.post(
            "/api/v1/pdf/export",
            json={
                "html_content": "<h1>Report</h1>",
                "filename": "report.pdf",
                "user_id": "user-1",
            },
        )
        assert "report.pdf" in response.headers["content-disposition"]

    def test_export_returns_pdf_bytes_as_body(self, client):
        response = client.post(
            "/api/v1/pdf/export",
            json={
                "html_content": "<h1>Report</h1>",
                "filename": "report.pdf",
                "user_id": "user-1",
            },
        )
        assert response.content == b"%PDF-1.4 fake content"

    def test_export_with_css_and_base_url(self, client, mock_use_case):
        client.post(
            "/api/v1/pdf/export",
            json={
                "html_content": "<h1>Report</h1>",
                "filename": "report.pdf",
                "user_id": "user-1",
                "css_content": "body { color: red; }",
                "base_url": "https://example.com",
            },
        )
        call_args = mock_use_case.convert.call_args
        request = call_args.args[0]
        assert request.css_content == "body { color: red; }"
        assert request.base_url == "https://example.com"

    def test_export_missing_html_content_returns_422(self, client):
        response = client.post(
            "/api/v1/pdf/export",
            json={"filename": "report.pdf", "user_id": "user-1"},
        )
        assert response.status_code == 422

    def test_export_missing_user_id_returns_422(self, client):
        response = client.post(
            "/api/v1/pdf/export",
            json={"html_content": "<h1>Hi</h1>", "filename": "report.pdf"},
        )
        assert response.status_code == 422
