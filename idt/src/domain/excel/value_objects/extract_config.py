from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.domain.excel.value_objects.filter_condition import FilterCondition


@dataclass
class ExtractConfig:
    columns: Optional[List[str]] = None
    conditions: List[FilterCondition] = field(default_factory=list)
    drop_duplicates: bool = False
    drop_na: bool = False
    sort_by: Optional[str] = None
    sort_ascending: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "columns": self.columns,
            "conditions": [c.to_query_dict() for c in self.conditions],
            "drop_duplicates": self.drop_duplicates,
            "drop_na": self.drop_na,
            "sort_by": self.sort_by,
            "sort_ascending": self.sort_ascending,
        }
