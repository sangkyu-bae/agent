from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List


class FilterOperator(str, Enum):
    EQ = "EQ"
    NE = "NE"
    GT = "GT"
    LT = "LT"
    GTE = "GTE"
    LTE = "LTE"
    CONTAINS = "CONTAINS"
    STARTSWITH = "STARTSWITH"
    ENDSWITH = "ENDSWITH"
    ISIN = "ISIN"
    NOTNULL = "NOTNULL"
    ISNULL = "ISNULL"

    @classmethod
    def from_string(cls, value: str) -> "FilterOperator":
        upper_value = value.upper()
        for op in cls:
            if op.value == upper_value:
                return op
        raise ValueError(f"Invalid operator: {value}")


@dataclass(frozen=True)
class FilterCondition:
    column: str
    operator: FilterOperator
    value: Any = None
    case_sensitive: bool = True

    def __post_init__(self) -> None:
        if not self.column or not self.column.strip():
            raise ValueError("column cannot be empty or whitespace only")

        null_operators = {FilterOperator.NOTNULL, FilterOperator.ISNULL}
        if self.operator not in null_operators and self.value is None:
            raise ValueError(
                f"value is required for operator {self.operator.value}"
            )

        if self.operator == FilterOperator.ISIN:
            if not isinstance(self.value, list):
                raise ValueError("ISIN operator requires a list value")

    def to_query_dict(self) -> Dict[str, Any]:
        return {
            "column": self.column,
            "operator": self.operator.value,
            "value": self.value,
            "case_sensitive": self.case_sensitive,
        }
