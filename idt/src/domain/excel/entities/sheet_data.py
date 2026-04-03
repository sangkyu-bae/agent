from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class SheetData:
    sheet_name: str
    data: List[Dict[str, Any]]
    columns: List[str]
    dtypes: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.sheet_name or not self.sheet_name.strip():
            raise ValueError("sheet_name cannot be empty or whitespace only")

    @property
    def row_count(self) -> int:
        return len(self.data)

    @property
    def column_count(self) -> int:
        return len(self.columns)

    @property
    def is_empty(self) -> bool:
        return len(self.data) == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sheet_name": self.sheet_name,
            "data": self.data,
            "columns": self.columns,
            "dtypes": self.dtypes,
            "row_count": self.row_count,
            "column_count": self.column_count,
        }
