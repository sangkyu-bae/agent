from abc import ABC, abstractmethod
from typing import List

from src.domain.excel.entities.excel_data import ExcelData
from src.domain.excel.entities.sheet_data import SheetData


class ExcelParserInterface(ABC):
    @abstractmethod
    def parse(self, file_path: str, user_id: str) -> ExcelData:
        pass

    @abstractmethod
    def parse_bytes(
        self, file_bytes: bytes, filename: str, user_id: str
    ) -> ExcelData:
        pass

    @abstractmethod
    def parse_sheet(
        self, file_path: str, sheet_name: str, user_id: str
    ) -> SheetData:
        pass

    @abstractmethod
    def get_sheet_names(self, file_path: str) -> List[str]:
        pass

    @abstractmethod
    def get_parser_name(self) -> str:
        pass
