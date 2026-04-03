"""MySQLQueryCondition, MySQLPaginationParams, MySQLPageResult 스키마 단위 테스트."""
import pytest

from src.domain.mysql.schemas import (
    MySQLPageResult,
    MySQLPaginationParams,
    MySQLQueryCondition,
    VALID_OPERATORS,
)


class TestMySQLQueryCondition:
    def test_basic_fields(self):
        cond = MySQLQueryCondition(field="user_id", operator="eq", value="u-1")
        assert cond.field == "user_id"
        assert cond.operator == "eq"
        assert cond.value == "u-1"

    def test_all_valid_operators_accepted(self):
        for op in VALID_OPERATORS:
            cond = MySQLQueryCondition(field="col", operator=op, value="v")
            assert cond.operator == op

    def test_frozen(self):
        cond = MySQLQueryCondition(field="f", operator="eq", value="v")
        with pytest.raises((AttributeError, TypeError)):
            cond.field = "changed"  # type: ignore[misc]

    def test_list_value_for_in_operator(self):
        cond = MySQLQueryCondition(field="status", operator="in", value=["a", "b"])
        assert cond.value == ["a", "b"]


class TestMySQLPaginationParams:
    def test_defaults(self):
        p = MySQLPaginationParams()
        assert p.limit == 100
        assert p.offset == 0

    def test_custom_values(self):
        p = MySQLPaginationParams(limit=20, offset=40)
        assert p.limit == 20
        assert p.offset == 40

    def test_frozen(self):
        p = MySQLPaginationParams()
        with pytest.raises((AttributeError, TypeError)):
            p.limit = 999  # type: ignore[misc]


class TestMySQLPageResult:
    def test_fields(self):
        result = MySQLPageResult(items=["a", "b"], total=5, limit=2, offset=0)
        assert result.items == ["a", "b"]
        assert result.total == 5
        assert result.limit == 2
        assert result.offset == 0

    def test_has_more_true(self):
        result = MySQLPageResult(items=["a", "b"], total=5, limit=2, offset=0)
        assert result.has_more is True

    def test_has_more_false_when_exhausted(self):
        result = MySQLPageResult(items=["a", "b"], total=2, limit=2, offset=0)
        assert result.has_more is False

    def test_has_more_false_at_last_page(self):
        result = MySQLPageResult(items=["e"], total=5, limit=2, offset=4)
        assert result.has_more is False

    def test_empty_items(self):
        result = MySQLPageResult(items=[], total=0, limit=10, offset=0)
        assert result.has_more is False
