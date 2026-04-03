"""Domain schema tests for Excel export module. No mocks per CLAUDE.md."""
import pytest
from pydantic import ValidationError

from src.domain.excel_export.schemas import (
    ExcelExportRequest,
    ExcelExportResult,
    ExcelSheetData,
)


class TestExcelSheetData:
    def test_valid_sheet_data_creates_successfully(self):
        sheet = ExcelSheetData(
            sheet_name="Report",
            columns=["Name", "Score"],
            rows=[["Alice", 90], ["Bob", 85]],
        )
        assert sheet.sheet_name == "Report"
        assert len(sheet.columns) == 2
        assert len(sheet.rows) == 2

    def test_empty_columns_raises_validation_error(self):
        with pytest.raises(ValidationError):
            ExcelSheetData(sheet_name="Sheet1", columns=[], rows=[])

    def test_empty_sheet_name_raises_validation_error(self):
        with pytest.raises(ValidationError):
            ExcelSheetData(sheet_name="   ", columns=["A"], rows=[])

    def test_empty_rows_is_allowed(self):
        sheet = ExcelSheetData(sheet_name="Sheet1", columns=["A", "B"], rows=[])
        assert sheet.rows == []

    def test_default_sheet_name_is_sheet1(self):
        sheet = ExcelSheetData(columns=["A"], rows=[])
        assert sheet.sheet_name == "Sheet1"


class TestExcelExportRequest:
    def _valid_sheet(self) -> ExcelSheetData:
        return ExcelSheetData(columns=["Col1"], rows=[["val1"]])

    def test_valid_request_creates_successfully(self):
        req = ExcelExportRequest(
            filename="report.xlsx",
            sheets=[self._valid_sheet()],
            request_id="req-001",
            user_id="user-1",
        )
        assert req.filename == "report.xlsx"

    def test_filename_without_xlsx_gets_appended(self):
        req = ExcelExportRequest(
            filename="report",
            sheets=[self._valid_sheet()],
            request_id="req-001",
            user_id="user-1",
        )
        assert req.filename == "report.xlsx"

    def test_empty_filename_raises_validation_error(self):
        with pytest.raises(ValidationError):
            ExcelExportRequest(
                filename="   ",
                sheets=[self._valid_sheet()],
                request_id="req-001",
                user_id="user-1",
            )

    def test_empty_sheets_raises_validation_error(self):
        with pytest.raises(ValidationError):
            ExcelExportRequest(
                filename="report.xlsx",
                sheets=[],
                request_id="req-001",
                user_id="user-1",
            )

    def test_multiple_sheets_accepted(self):
        req = ExcelExportRequest(
            filename="report.xlsx",
            sheets=[self._valid_sheet(), self._valid_sheet()],
            request_id="req-001",
            user_id="user-1",
        )
        assert len(req.sheets) == 2


class TestExcelExportResult:
    def test_valid_result_creates_successfully(self):
        result = ExcelExportResult(
            filename="report.xlsx",
            user_id="user-1",
            request_id="req-001",
            excel_bytes=b"PK fake excel bytes",
            size_bytes=19,
            sheet_count=1,
            exporter_used="pandas+openpyxl",
        )
        assert result.sheet_count == 1
        assert result.exporter_used == "pandas+openpyxl"
