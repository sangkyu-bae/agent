import pytest
from datetime import datetime
from typing import Dict

from src.domain.excel.entities.excel_data import ExcelData
from src.domain.excel.entities.sheet_data import SheetData
from src.domain.excel.value_objects.excel_metadata import ExcelMetadata


class TestExcelDataCreation:
    def test_create_excel_data_with_required_fields(self):
        sheet = SheetData(
            sheet_name="Sheet1",
            data=[{"col": "val"}],
            columns=["col"],
        )
        metadata = ExcelMetadata(
            file_id="file-123",
            filename="test.xlsx",
            sheet_names=["Sheet1"],
            total_rows=1,
            user_id="user-1",
        )
        excel_data = ExcelData(
            file_id="file-123",
            filename="test.xlsx",
            sheets={"Sheet1": sheet},
            metadata=metadata,
        )
        assert excel_data.file_id == "file-123"
        assert excel_data.filename == "test.xlsx"
        assert "Sheet1" in excel_data.sheets

    def test_create_excel_data_with_multiple_sheets(self):
        sheet1 = SheetData(
            sheet_name="Sheet1",
            data=[{"a": 1}],
            columns=["a"],
        )
        sheet2 = SheetData(
            sheet_name="Sheet2",
            data=[{"b": 2}],
            columns=["b"],
        )
        metadata = ExcelMetadata(
            file_id="file-456",
            filename="multi.xlsx",
            sheet_names=["Sheet1", "Sheet2"],
            total_rows=2,
            user_id="user-1",
        )
        excel_data = ExcelData(
            file_id="file-456",
            filename="multi.xlsx",
            sheets={"Sheet1": sheet1, "Sheet2": sheet2},
            metadata=metadata,
        )
        assert len(excel_data.sheets) == 2
        assert excel_data.sheets["Sheet1"].sheet_name == "Sheet1"
        assert excel_data.sheets["Sheet2"].sheet_name == "Sheet2"


class TestExcelDataValidation:
    def test_file_id_cannot_be_empty(self):
        sheet = SheetData(
            sheet_name="Sheet1",
            data=[],
            columns=[],
        )
        metadata = ExcelMetadata(
            file_id="valid-id",
            filename="test.xlsx",
            sheet_names=["Sheet1"],
            total_rows=0,
            user_id="user-1",
        )
        with pytest.raises(ValueError):
            ExcelData(
                file_id="",
                filename="test.xlsx",
                sheets={"Sheet1": sheet},
                metadata=metadata,
            )

    def test_filename_cannot_be_empty(self):
        sheet = SheetData(
            sheet_name="Sheet1",
            data=[],
            columns=[],
        )
        metadata = ExcelMetadata(
            file_id="file-123",
            filename="valid.xlsx",
            sheet_names=["Sheet1"],
            total_rows=0,
            user_id="user-1",
        )
        with pytest.raises(ValueError):
            ExcelData(
                file_id="file-123",
                filename="",
                sheets={"Sheet1": sheet},
                metadata=metadata,
            )


class TestExcelDataProperties:
    def test_sheet_names_property(self):
        sheet1 = SheetData(
            sheet_name="Data",
            data=[],
            columns=[],
        )
        sheet2 = SheetData(
            sheet_name="Summary",
            data=[],
            columns=[],
        )
        metadata = ExcelMetadata(
            file_id="file-123",
            filename="test.xlsx",
            sheet_names=["Data", "Summary"],
            total_rows=0,
            user_id="user-1",
        )
        excel_data = ExcelData(
            file_id="file-123",
            filename="test.xlsx",
            sheets={"Data": sheet1, "Summary": sheet2},
            metadata=metadata,
        )
        assert set(excel_data.sheet_names) == {"Data", "Summary"}

    def test_total_rows_property(self):
        sheet1 = SheetData(
            sheet_name="Sheet1",
            data=[{"a": 1}, {"a": 2}],
            columns=["a"],
        )
        sheet2 = SheetData(
            sheet_name="Sheet2",
            data=[{"b": 1}, {"b": 2}, {"b": 3}],
            columns=["b"],
        )
        metadata = ExcelMetadata(
            file_id="file-123",
            filename="test.xlsx",
            sheet_names=["Sheet1", "Sheet2"],
            total_rows=5,
            user_id="user-1",
        )
        excel_data = ExcelData(
            file_id="file-123",
            filename="test.xlsx",
            sheets={"Sheet1": sheet1, "Sheet2": sheet2},
            metadata=metadata,
        )
        assert excel_data.total_rows == 5

    def test_get_sheet_returns_sheet_data(self):
        sheet = SheetData(
            sheet_name="Sheet1",
            data=[{"a": 1}],
            columns=["a"],
        )
        metadata = ExcelMetadata(
            file_id="file-123",
            filename="test.xlsx",
            sheet_names=["Sheet1"],
            total_rows=1,
            user_id="user-1",
        )
        excel_data = ExcelData(
            file_id="file-123",
            filename="test.xlsx",
            sheets={"Sheet1": sheet},
            metadata=metadata,
        )
        result = excel_data.get_sheet("Sheet1")
        assert result == sheet

    def test_get_sheet_not_found_returns_none(self):
        sheet = SheetData(
            sheet_name="Sheet1",
            data=[],
            columns=[],
        )
        metadata = ExcelMetadata(
            file_id="file-123",
            filename="test.xlsx",
            sheet_names=["Sheet1"],
            total_rows=0,
            user_id="user-1",
        )
        excel_data = ExcelData(
            file_id="file-123",
            filename="test.xlsx",
            sheets={"Sheet1": sheet},
            metadata=metadata,
        )
        result = excel_data.get_sheet("NonExistent")
        assert result is None


class TestExcelDataToDict:
    def test_to_dict_contains_all_fields(self):
        sheet = SheetData(
            sheet_name="Sheet1",
            data=[{"a": 1}],
            columns=["a"],
        )
        metadata = ExcelMetadata(
            file_id="file-123",
            filename="test.xlsx",
            sheet_names=["Sheet1"],
            total_rows=1,
            user_id="user-1",
        )
        excel_data = ExcelData(
            file_id="file-123",
            filename="test.xlsx",
            sheets={"Sheet1": sheet},
            metadata=metadata,
        )
        result = excel_data.to_dict()

        assert result["file_id"] == "file-123"
        assert result["filename"] == "test.xlsx"
        assert "Sheet1" in result["sheets"]
        assert "metadata" in result
