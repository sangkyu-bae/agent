"""Application layer tests for HtmlToPdfUseCase.

Uses Mock for infrastructure dependencies (converter, logger).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.use_cases.html_to_pdf_use_case import HtmlToPdfUseCase
from src.domain.pdf_export.schemas import HtmlToPdfRequest, HtmlToPdfResult


@pytest.fixture
def mock_converter():
    converter = MagicMock()
    converter.get_converter_name.return_value = "xhtml2pdf"
    converter.convert.return_value = b"%PDF-1.4 content"
    return converter


@pytest.fixture
def mock_logger():
    return MagicMock()


@pytest.fixture
def use_case(mock_converter, mock_logger):
    return HtmlToPdfUseCase(converter=mock_converter, logger=mock_logger)


@pytest.fixture
def valid_request():
    return HtmlToPdfRequest(
        html_content="<h1>Report</h1>",
        filename="report.pdf",
        request_id="req-001",
        user_id="user-1",
    )


class TestHtmlToPdfUseCase:
    async def test_convert_returns_html_to_pdf_result(self, use_case, valid_request):
        result = await use_case.convert(valid_request)

        assert isinstance(result, HtmlToPdfResult)
        assert result.filename == "report.pdf"
        assert result.user_id == "user-1"
        assert result.request_id == "req-001"
        assert result.pdf_bytes == b"%PDF-1.4 content"
        assert result.size_bytes == len(b"%PDF-1.4 content")
        assert result.converter_used == "xhtml2pdf"

    async def test_convert_calls_converter_with_correct_args(
        self, use_case, valid_request, mock_converter
    ):
        await use_case.convert(valid_request)

        mock_converter.convert.assert_called_once_with(
            html_content="<h1>Report</h1>",
            css_content=None,
            base_url=None,
        )

    async def test_convert_passes_css_and_base_url(
        self, use_case, mock_converter
    ):
        request = HtmlToPdfRequest(
            html_content="<h1>Report</h1>",
            filename="report.pdf",
            request_id="req-001",
            user_id="user-1",
            css_content="body { color: red; }",
            base_url="https://example.com",
        )
        await use_case.convert(request)

        mock_converter.convert.assert_called_once_with(
            html_content="<h1>Report</h1>",
            css_content="body { color: red; }",
            base_url="https://example.com",
        )

    async def test_convert_logs_info_on_start_and_complete(
        self, use_case, valid_request, mock_logger
    ):
        await use_case.convert(valid_request)

        assert mock_logger.info.call_count >= 2

    async def test_convert_logs_request_id_in_every_log(
        self, use_case, valid_request, mock_logger
    ):
        await use_case.convert(valid_request)

        for call in mock_logger.info.call_args_list:
            kwargs = call.kwargs
            assert "request_id" in kwargs

    async def test_convert_logs_error_and_reraises_on_exception(
        self, use_case, valid_request, mock_converter, mock_logger
    ):
        mock_converter.convert.side_effect = RuntimeError("convert failed")

        with pytest.raises(RuntimeError, match="convert failed"):
            await use_case.convert(valid_request)

        mock_logger.error.assert_called_once()
        error_kwargs = mock_logger.error.call_args.kwargs
        assert "exception" in error_kwargs
        assert "request_id" in error_kwargs

    async def test_convert_runs_in_thread_to_avoid_blocking(
        self, mock_converter, mock_logger, valid_request
    ):
        """converter.convert는 sync 함수 → asyncio.to_thread로 실행."""
        with patch(
            "src.application.use_cases.html_to_pdf_use_case.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=b"%PDF-1.4 content",
        ) as mock_to_thread:
            use_case = HtmlToPdfUseCase(converter=mock_converter, logger=mock_logger)
            await use_case.convert(valid_request)

        mock_to_thread.assert_called_once()
