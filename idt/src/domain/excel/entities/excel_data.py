from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.domain.excel.entities.sheet_data import SheetData
from src.domain.excel.value_objects.excel_metadata import ExcelMetadata


@dataclass
class ExcelData:
    file_id: str
    filename: str
    sheets: Dict[str, SheetData]
    metadata: ExcelMetadata

    def __post_init__(self) -> None:
        if not self.file_id or not self.file_id.strip():
            raise ValueError("file_id cannot be empty")
        if not self.filename or not self.filename.strip():
            raise ValueError("filename cannot be empty")

    @property
    def sheet_names(self) -> List[str]:
        return list(self.sheets.keys())

    @property
    def total_rows(self) -> int:
        return sum(sheet.row_count for sheet in self.sheets.values())

    def get_sheet(self, sheet_name: str) -> Optional[SheetData]:
        return self.sheets.get(sheet_name)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_id": self.file_id,
            "filename": self.filename,
            "sheets": {
                name: sheet.to_dict() for name, sheet in self.sheets.items()
            },
            "metadata": self.metadata.to_dict(),
        }
