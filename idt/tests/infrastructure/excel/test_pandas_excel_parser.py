import pytest
from pathlib import Path

from src.domain.excel.interfaces.excel_parser_interface import ExcelParserInterface
from src.domain.excel.entities.excel_data import ExcelData
from src.domain.excel.entities.sheet_data import SheetData
from src.infrastructure.excel.pandas_excel_parser import PandasExcelParser


class TestPandasExcelParser:
    def test_implements_excel_parser_interface(self):
        parser = PandasExcelParser()
        assert isinstance(parser, ExcelParserInterface)

    def test_get_parser_name_returns_pandas(self):
        parser = PandasExcelParser()
        assert parser.get_parser_name() == "pandas"


class TestPandasExcelParserGetSheetNames:
    def test_get_sheet_names_returns_list(self, single_sheet_excel: Path):
        parser = PandasExcelParser()
        sheet_names = parser.get_sheet_names(str(single_sheet_excel))
        assert isinstance(sheet_names, list)
        assert "Sheet1" in sheet_names

    def test_get_sheet_names_multiple_sheets(self, multi_sheet_excel: Path):
        parser = PandasExcelParser()
        sheet_names = parser.get_sheet_names(str(multi_sheet_excel))
        assert len(sheet_names) == 2
        assert "Users" in sheet_names
        assert "Orders" in sheet_names

    def test_get_sheet_names_file_not_found_raises_error(self, tmp_path: Path):
        parser = PandasExcelParser()
        with pytest.raises(FileNotFoundError):
            parser.get_sheet_names(str(tmp_path / "nonexistent.xlsx"))


class TestPandasExcelParserParse:
    def test_parse_single_sheet_excel(self, single_sheet_excel: Path):
        parser = PandasExcelParser()
        result = parser.parse(str(single_sheet_excel), "user-1")

        assert isinstance(result, ExcelData)
        assert len(result.sheets) == 1
        assert "Sheet1" in result.sheets

    def test_parse_multi_sheet_excel(self, multi_sheet_excel: Path):
        parser = PandasExcelParser()
        result = parser.parse(str(multi_sheet_excel), "user-1")

        assert len(result.sheets) == 2
        assert "Users" in result.sheets
        assert "Orders" in result.sheets

    def test_parse_xlsx_file(self, single_sheet_excel: Path):
        parser = PandasExcelParser()
        result = parser.parse(str(single_sheet_excel), "user-1")

        sheet = result.get_sheet("Sheet1")
        assert sheet is not None
        assert sheet.row_count == 2
        assert "name" in sheet.columns
        assert "age" in sheet.columns
        assert "city" in sheet.columns

    def test_parse_empty_excel_returns_empty_sheets(self, empty_excel: Path):
        parser = PandasExcelParser()
        result = parser.parse(str(empty_excel), "user-1")

        assert "EmptySheet" in result.sheets
        sheet = result.get_sheet("EmptySheet")
        assert sheet.row_count == 0

    def test_parse_nonexistent_file_raises_error(self, tmp_path: Path):
        parser = PandasExcelParser()
        with pytest.raises(FileNotFoundError):
            parser.parse(str(tmp_path / "nonexistent.xlsx"), "user-1")

    def test_parse_extracts_filename_from_path(self, single_sheet_excel: Path):
        parser = PandasExcelParser()
        result = parser.parse(str(single_sheet_excel), "user-1")

        assert result.filename == "single_sheet.xlsx"
        assert result.metadata.filename == "single_sheet.xlsx"

    def test_parse_sets_user_id_in_metadata(self, single_sheet_excel: Path):
        parser = PandasExcelParser()
        result = parser.parse(str(single_sheet_excel), "test-user-123")

        assert result.metadata.user_id == "test-user-123"

    def test_parse_auto_detects_header(self, single_sheet_excel: Path):
        parser = PandasExcelParser()
        result = parser.parse(str(single_sheet_excel), "user-1")

        sheet = result.get_sheet("Sheet1")
        data = sheet.data
        assert len(data) == 2
        assert data[0]["name"] == "John"
        assert data[1]["name"] == "Jane"


class TestPandasExcelParserParseBytes:
    def test_parse_bytes_single_sheet(self, single_sheet_excel_bytes: bytes):
        parser = PandasExcelParser()
        result = parser.parse_bytes(
            single_sheet_excel_bytes, "uploaded.xlsx", "user-1"
        )

        assert isinstance(result, ExcelData)
        assert "Sheet1" in result.sheets
        sheet = result.get_sheet("Sheet1")
        assert sheet.row_count == 2

    def test_parse_bytes_sets_filename_metadata(self, single_sheet_excel_bytes: bytes):
        parser = PandasExcelParser()
        result = parser.parse_bytes(
            single_sheet_excel_bytes, "custom_name.xlsx", "user-1"
        )

        assert result.filename == "custom_name.xlsx"
        assert result.metadata.filename == "custom_name.xlsx"

    def test_parse_bytes_invalid_format_raises_error(self):
        parser = PandasExcelParser()
        invalid_bytes = b"this is not an excel file"
        with pytest.raises(ValueError):
            parser.parse_bytes(invalid_bytes, "invalid.xlsx", "user-1")


class TestPandasExcelParserParseSheet:
    def test_parse_sheet_returns_sheet_data(self, multi_sheet_excel: Path):
        parser = PandasExcelParser()
        result = parser.parse_sheet(str(multi_sheet_excel), "Users", "user-1")

        assert isinstance(result, SheetData)
        assert result.sheet_name == "Users"
        assert result.row_count == 2
        assert "id" in result.columns
        assert "name" in result.columns

    def test_parse_sheet_not_found_raises_error(self, single_sheet_excel: Path):
        parser = PandasExcelParser()
        with pytest.raises(ValueError):
            parser.parse_sheet(str(single_sheet_excel), "NonExistent", "user-1")

    def test_parse_sheet_row_count_column_count(self, multi_sheet_excel: Path):
        parser = PandasExcelParser()
        result = parser.parse_sheet(str(multi_sheet_excel), "Orders", "user-1")

        assert result.row_count == 3
        assert result.column_count == 3
        assert result.columns == ["order_id", "user_id", "amount"]
