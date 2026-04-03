"""Domain schema tests for HTML to PDF module.

Domain tests use NO mocks per CLAUDE.md rule.
"""
import pytest
from pydantic import ValidationError

from src.domain.pdf_export.schemas import HtmlToPdfRequest, HtmlToPdfResult


class TestHtmlToPdfRequest:
    def test_valid_request_creates_successfully(self):
        req = HtmlToPdfRequest(
            html_content="<h1>Hello</h1>",
            filename="report.pdf",
            request_id="req-001",
            user_id="user-1",
        )
        assert req.html_content == "<h1>Hello</h1>"
        assert req.filename == "report.pdf"

    def test_empty_html_content_raises_validation_error(self):
        with pytest.raises(ValidationError):
            HtmlToPdfRequest(
                html_content="   ",
                filename="report.pdf",
                request_id="req-001",
                user_id="user-1",
            )

    def test_empty_filename_raises_validation_error(self):
        with pytest.raises(ValidationError):
            HtmlToPdfRequest(
                html_content="<p>content</p>",
                filename="   ",
                request_id="req-001",
                user_id="user-1",
            )

    def test_filename_without_pdf_extension_gets_appended(self):
        req = HtmlToPdfRequest(
            html_content="<p>content</p>",
            filename="report",
            request_id="req-001",
            user_id="user-1",
        )
        assert req.filename == "report.pdf"

    def test_filename_with_pdf_extension_stays_unchanged(self):
        req = HtmlToPdfRequest(
            html_content="<p>content</p>",
            filename="report.pdf",
            request_id="req-001",
            user_id="user-1",
        )
        assert req.filename == "report.pdf"

    def test_optional_css_content_defaults_to_none(self):
        req = HtmlToPdfRequest(
            html_content="<p>content</p>",
            filename="report.pdf",
            request_id="req-001",
            user_id="user-1",
        )
        assert req.css_content is None

    def test_optional_base_url_defaults_to_none(self):
        req = HtmlToPdfRequest(
            html_content="<p>content</p>",
            filename="report.pdf",
            request_id="req-001",
            user_id="user-1",
        )
        assert req.base_url is None

    def test_css_content_and_base_url_accepted(self):
        req = HtmlToPdfRequest(
            html_content="<p>content</p>",
            filename="report.pdf",
            request_id="req-001",
            user_id="user-1",
            css_content="body { font-size: 12pt; }",
            base_url="https://example.com",
        )
        assert req.css_content == "body { font-size: 12pt; }"
        assert req.base_url == "https://example.com"


class TestHtmlToPdfResult:
    def test_valid_result_creates_successfully(self):
        result = HtmlToPdfResult(
            filename="report.pdf",
            user_id="user-1",
            request_id="req-001",
            pdf_bytes=b"%PDF-1.4 content",
            size_bytes=16,
            converter_used="weasyprint",
        )
        assert result.size_bytes == 16
        assert result.converter_used == "weasyprint"
        assert result.pdf_bytes == b"%PDF-1.4 content"
