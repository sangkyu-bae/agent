"""Application layer tests for ExcelExportUseCase."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.use_cases.excel_export_use_case import ExcelExportUseCase
from src.domain.excel_export.schemas import (
    ExcelExportRequest,
    ExcelExportResult,
    ExcelSheetData,
)


@pytest.fixture
def mock_exporter():
    exporter = MagicMock()
    exporter.get_exporter_name.return_value = "pandas+openpyxl"
    exporter.export.return_value = ExcelExportResult(
        filename="report.xlsx",
        user_id="user-1",
        request_id="req-001",
        excel_bytes=b"PK fake",
        size_bytes=7,
        sheet_count=1,
        exporter_used="pandas+openpyxl",
    )
    return exporter


@pytest.fixture
def mock_logger():
    return MagicMock()


@pytest.fixture
def use_case(mock_exporter, mock_logger):
    return ExcelExportUseCase(exporter=mock_exporter, logger=mock_logger)


@pytest.fixture
def valid_request():
    return ExcelExportRequest(
        filename="report.xlsx",
        sheets=[ExcelSheetData(columns=["A", "B"], rows=[[1, 2]])],
        request_id="req-001",
        user_id="user-1",
    )


class TestExcelExportUseCase:
    async def test_export_returns_excel_export_result(self, use_case, valid_request):
        result = await use_case.export(valid_request)

        assert isinstance(result, ExcelExportResult)
        assert result.filename == "report.xlsx"
        assert result.excel_bytes == b"PK fake"
        assert result.exporter_used == "pandas+openpyxl"

    async def test_export_calls_exporter_with_request(
        self, use_case, valid_request, mock_exporter
    ):
        await use_case.export(valid_request)
        mock_exporter.export.assert_called_once_with(valid_request)

    async def test_export_logs_info_on_start_and_complete(
        self, use_case, valid_request, mock_logger
    ):
        await use_case.export(valid_request)
        assert mock_logger.info.call_count >= 2

    async def test_export_logs_request_id_in_every_log(
        self, use_case, valid_request, mock_logger
    ):
        await use_case.export(valid_request)
        for call in mock_logger.info.call_args_list:
            assert "request_id" in call.kwargs

    async def test_export_logs_error_and_reraises_on_exception(
        self, use_case, valid_request, mock_exporter, mock_logger
    ):
        mock_exporter.export.side_effect = RuntimeError("exporter failed")

        with pytest.raises(RuntimeError, match="exporter failed"):
            await use_case.export(valid_request)

        mock_logger.error.assert_called_once()
        assert "exception" in mock_logger.error.call_args.kwargs
        assert "request_id" in mock_logger.error.call_args.kwargs

    async def test_export_runs_in_thread_to_avoid_blocking(
        self, mock_exporter, mock_logger, valid_request
    ):
        from unittest.mock import patch

        with patch(
            "src.application.use_cases.excel_export_use_case.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=mock_exporter.export.return_value,
        ) as mock_to_thread:
            use_case = ExcelExportUseCase(exporter=mock_exporter, logger=mock_logger)
            await use_case.export(valid_request)

        mock_to_thread.assert_called_once()
