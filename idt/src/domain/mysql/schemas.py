"""MySQL 공통 Repository 도메인 스키마: 순수 Value Object."""
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")

VALID_OPERATORS = frozenset({"eq", "ne", "gt", "lt", "gte", "lte", "like", "in"})


@dataclass(frozen=True)
class MySQLQueryCondition:
    """단일 WHERE 필터 조건.

    Attributes:
        field:    모델 컬럼명 (예: "user_id", "status")
        operator: 연산자 — eq | ne | gt | lt | gte | lte | like | in
        value:    비교 값 (in 연산자의 경우 list)
    """

    field: str
    operator: str
    value: Any


@dataclass(frozen=True)
class MySQLPaginationParams:
    """페이지네이션 파라미터."""

    limit: int = 100
    offset: int = 0


@dataclass(frozen=True)
class MySQLPageResult(Generic[T]):
    """페이지네이션 결과 래퍼.

    Attributes:
        items:  현재 페이지 항목
        total:  전체 건수
        limit:  요청 limit
        offset: 요청 offset
    """

    items: list[T]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        """다음 페이지 존재 여부."""
        return self.offset + len(self.items) < self.total
