import pytest
from abc import ABC
from typing import List

from src.domain.excel.interfaces.excel_parser_interface import ExcelParserInterface
from src.domain.excel.entities.excel_data import ExcelData
from src.domain.excel.entities.sheet_data import SheetData


class TestExcelParserInterface:
    def test_is_abstract_class(self):
        assert issubclass(ExcelParserInterface, ABC)

    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            ExcelParserInterface()

    def test_has_parse_method(self):
        assert hasattr(ExcelParserInterface, "parse")
        assert callable(getattr(ExcelParserInterface, "parse"))

    def test_has_parse_bytes_method(self):
        assert hasattr(ExcelParserInterface, "parse_bytes")
        assert callable(getattr(ExcelParserInterface, "parse_bytes"))

    def test_has_parse_sheet_method(self):
        assert hasattr(ExcelParserInterface, "parse_sheet")
        assert callable(getattr(ExcelParserInterface, "parse_sheet"))

    def test_has_get_sheet_names_method(self):
        assert hasattr(ExcelParserInterface, "get_sheet_names")
        assert callable(getattr(ExcelParserInterface, "get_sheet_names"))

    def test_has_get_parser_name_method(self):
        assert hasattr(ExcelParserInterface, "get_parser_name")
        assert callable(getattr(ExcelParserInterface, "get_parser_name"))


class TestExcelParserInterfaceImplementation:
    def test_incomplete_implementation_raises_error(self):
        class IncompleteParser(ExcelParserInterface):
            def parse(self, file_path: str, user_id: str) -> ExcelData:
                pass

        with pytest.raises(TypeError):
            IncompleteParser()

    def test_complete_implementation_can_be_instantiated(self):
        class CompleteParser(ExcelParserInterface):
            def parse(self, file_path: str, user_id: str) -> ExcelData:
                pass

            def parse_bytes(
                self, file_bytes: bytes, filename: str, user_id: str
            ) -> ExcelData:
                pass

            def parse_sheet(
                self, file_path: str, sheet_name: str, user_id: str
            ) -> SheetData:
                pass

            def get_sheet_names(self, file_path: str) -> List[str]:
                pass

            def get_parser_name(self) -> str:
                return "complete"

        parser = CompleteParser()
        assert parser.get_parser_name() == "complete"
