import pytest
from typing import Dict, List, Any

from src.domain.excel.entities.sheet_data import SheetData


class TestSheetDataCreation:
    def test_create_sheet_data_with_required_fields(self):
        data = [
            {"name": "John", "age": 30},
            {"name": "Jane", "age": 25},
        ]
        sheet = SheetData(
            sheet_name="Sheet1",
            data=data,
            columns=["name", "age"],
        )
        assert sheet.sheet_name == "Sheet1"
        assert sheet.data == data
        assert sheet.columns == ["name", "age"]

    def test_create_sheet_data_with_dtypes(self):
        dtypes = {"name": "str", "age": "int64"}
        sheet = SheetData(
            sheet_name="Sheet1",
            data=[],
            columns=["name", "age"],
            dtypes=dtypes,
        )
        assert sheet.dtypes == dtypes

    def test_dtypes_default_is_empty_dict(self):
        sheet = SheetData(
            sheet_name="Sheet1",
            data=[],
            columns=[],
        )
        assert sheet.dtypes == {}


class TestSheetDataValidation:
    def test_sheet_name_cannot_be_empty(self):
        with pytest.raises(ValueError):
            SheetData(
                sheet_name="",
                data=[],
                columns=[],
            )

    def test_sheet_name_cannot_be_whitespace_only(self):
        with pytest.raises(ValueError):
            SheetData(
                sheet_name="   ",
                data=[],
                columns=[],
            )


class TestSheetDataProperties:
    def test_row_count(self):
        data = [
            {"name": "A"},
            {"name": "B"},
            {"name": "C"},
        ]
        sheet = SheetData(
            sheet_name="Sheet1",
            data=data,
            columns=["name"],
        )
        assert sheet.row_count == 3

    def test_row_count_empty_data(self):
        sheet = SheetData(
            sheet_name="Sheet1",
            data=[],
            columns=["name"],
        )
        assert sheet.row_count == 0

    def test_column_count(self):
        sheet = SheetData(
            sheet_name="Sheet1",
            data=[],
            columns=["a", "b", "c", "d"],
        )
        assert sheet.column_count == 4

    def test_column_count_empty_columns(self):
        sheet = SheetData(
            sheet_name="Sheet1",
            data=[],
            columns=[],
        )
        assert sheet.column_count == 0

    def test_is_empty_true(self):
        sheet = SheetData(
            sheet_name="Sheet1",
            data=[],
            columns=["a"],
        )
        assert sheet.is_empty is True

    def test_is_empty_false(self):
        sheet = SheetData(
            sheet_name="Sheet1",
            data=[{"a": 1}],
            columns=["a"],
        )
        assert sheet.is_empty is False


class TestSheetDataToDict:
    def test_to_dict_contains_all_fields(self):
        data = [{"name": "John"}]
        sheet = SheetData(
            sheet_name="Sheet1",
            data=data,
            columns=["name"],
            dtypes={"name": "str"},
        )
        result = sheet.to_dict()

        assert result["sheet_name"] == "Sheet1"
        assert result["data"] == data
        assert result["columns"] == ["name"]
        assert result["dtypes"] == {"name": "str"}
        assert result["row_count"] == 1
        assert result["column_count"] == 1
