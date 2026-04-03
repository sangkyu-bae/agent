from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List


@dataclass(frozen=True)
class ExcelMetadata:
    file_id: str
    filename: str
    sheet_names: List[str]
    total_rows: int
    user_id: str
    parsed_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        if not self.file_id or not self.file_id.strip():
            raise ValueError("file_id cannot be empty")
        if not self.filename or not self.filename.strip():
            raise ValueError("filename cannot be empty")
        if not self.user_id or not self.user_id.strip():
            raise ValueError("user_id cannot be empty")
        if self.total_rows < 0:
            raise ValueError("total_rows cannot be negative")

    @property
    def sheet_count(self) -> int:
        return len(self.sheet_names)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_id": self.file_id,
            "filename": self.filename,
            "sheet_names": self.sheet_names,
            "total_rows": self.total_rows,
            "user_id": self.user_id,
            "parsed_at": self.parsed_at.isoformat(),
            "sheet_count": self.sheet_count,
        }
