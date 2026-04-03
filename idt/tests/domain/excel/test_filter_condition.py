import pytest
from typing import Any

from src.domain.excel.value_objects.filter_condition import (
    FilterOperator,
    FilterCondition,
)


class TestFilterOperatorEnum:
    def test_all_operators_have_values(self):
        expected_operators = [
            "EQ", "NE", "GT", "LT", "GTE", "LTE",
            "CONTAINS", "STARTSWITH", "ENDSWITH",
            "ISIN", "NOTNULL", "ISNULL"
        ]
        actual_operators = [op.name for op in FilterOperator]
        assert len(actual_operators) == 12
        for op in expected_operators:
            assert op in actual_operators

    def test_from_string_valid_operators(self):
        assert FilterOperator.from_string("EQ") == FilterOperator.EQ
        assert FilterOperator.from_string("NE") == FilterOperator.NE
        assert FilterOperator.from_string("GT") == FilterOperator.GT
        assert FilterOperator.from_string("LT") == FilterOperator.LT
        assert FilterOperator.from_string("GTE") == FilterOperator.GTE
        assert FilterOperator.from_string("LTE") == FilterOperator.LTE
        assert FilterOperator.from_string("CONTAINS") == FilterOperator.CONTAINS
        assert FilterOperator.from_string("STARTSWITH") == FilterOperator.STARTSWITH
        assert FilterOperator.from_string("ENDSWITH") == FilterOperator.ENDSWITH
        assert FilterOperator.from_string("ISIN") == FilterOperator.ISIN
        assert FilterOperator.from_string("NOTNULL") == FilterOperator.NOTNULL
        assert FilterOperator.from_string("ISNULL") == FilterOperator.ISNULL

    def test_from_string_case_insensitive(self):
        assert FilterOperator.from_string("eq") == FilterOperator.EQ
        assert FilterOperator.from_string("Eq") == FilterOperator.EQ
        assert FilterOperator.from_string("contains") == FilterOperator.CONTAINS
        assert FilterOperator.from_string("Contains") == FilterOperator.CONTAINS

    def test_from_string_invalid_raises_error(self):
        with pytest.raises(ValueError):
            FilterOperator.from_string("INVALID")
        with pytest.raises(ValueError):
            FilterOperator.from_string("")
        with pytest.raises(ValueError):
            FilterOperator.from_string("EQUALS")


class TestFilterConditionCreation:
    def test_create_eq_filter(self):
        condition = FilterCondition(
            column="name",
            operator=FilterOperator.EQ,
            value="John"
        )
        assert condition.column == "name"
        assert condition.operator == FilterOperator.EQ
        assert condition.value == "John"

    def test_create_numeric_comparison_filter(self):
        gt_condition = FilterCondition(
            column="age",
            operator=FilterOperator.GT,
            value=18
        )
        assert gt_condition.operator == FilterOperator.GT
        assert gt_condition.value == 18

        lt_condition = FilterCondition(
            column="price",
            operator=FilterOperator.LT,
            value=100.5
        )
        assert lt_condition.operator == FilterOperator.LT
        assert lt_condition.value == 100.5

        gte_condition = FilterCondition(
            column="quantity",
            operator=FilterOperator.GTE,
            value=0
        )
        assert gte_condition.operator == FilterOperator.GTE

        lte_condition = FilterCondition(
            column="score",
            operator=FilterOperator.LTE,
            value=100
        )
        assert lte_condition.operator == FilterOperator.LTE

    def test_create_string_filter(self):
        contains = FilterCondition(
            column="description",
            operator=FilterOperator.CONTAINS,
            value="important"
        )
        assert contains.operator == FilterOperator.CONTAINS

        startswith = FilterCondition(
            column="code",
            operator=FilterOperator.STARTSWITH,
            value="PRD"
        )
        assert startswith.operator == FilterOperator.STARTSWITH

        endswith = FilterCondition(
            column="email",
            operator=FilterOperator.ENDSWITH,
            value="@example.com"
        )
        assert endswith.operator == FilterOperator.ENDSWITH

    def test_create_isin_filter_with_list(self):
        condition = FilterCondition(
            column="status",
            operator=FilterOperator.ISIN,
            value=["active", "pending", "review"]
        )
        assert condition.operator == FilterOperator.ISIN
        assert condition.value == ["active", "pending", "review"]

    def test_create_null_filters(self):
        notnull = FilterCondition(
            column="email",
            operator=FilterOperator.NOTNULL
        )
        assert notnull.operator == FilterOperator.NOTNULL
        assert notnull.value is None

        isnull = FilterCondition(
            column="deleted_at",
            operator=FilterOperator.ISNULL
        )
        assert isnull.operator == FilterOperator.ISNULL
        assert isnull.value is None

    def test_case_sensitive_default_true(self):
        condition = FilterCondition(
            column="name",
            operator=FilterOperator.EQ,
            value="John"
        )
        assert condition.case_sensitive is True

    def test_case_sensitive_can_be_false(self):
        condition = FilterCondition(
            column="name",
            operator=FilterOperator.CONTAINS,
            value="john",
            case_sensitive=False
        )
        assert condition.case_sensitive is False


class TestFilterConditionValidation:
    def test_column_cannot_be_empty(self):
        with pytest.raises(ValueError):
            FilterCondition(
                column="",
                operator=FilterOperator.EQ,
                value="test"
            )

    def test_column_cannot_be_whitespace_only(self):
        with pytest.raises(ValueError):
            FilterCondition(
                column="   ",
                operator=FilterOperator.EQ,
                value="test"
            )

    def test_value_can_be_none_for_null_operators(self):
        notnull = FilterCondition(
            column="field",
            operator=FilterOperator.NOTNULL,
            value=None
        )
        assert notnull.value is None

        isnull = FilterCondition(
            column="field",
            operator=FilterOperator.ISNULL,
            value=None
        )
        assert isnull.value is None

    def test_value_required_for_non_null_operators(self):
        with pytest.raises(ValueError):
            FilterCondition(
                column="name",
                operator=FilterOperator.EQ,
                value=None
            )
        with pytest.raises(ValueError):
            FilterCondition(
                column="age",
                operator=FilterOperator.GT,
                value=None
            )

    def test_isin_value_must_be_list(self):
        with pytest.raises(ValueError):
            FilterCondition(
                column="status",
                operator=FilterOperator.ISIN,
                value="single_value"
            )
        with pytest.raises(ValueError):
            FilterCondition(
                column="status",
                operator=FilterOperator.ISIN,
                value=123
            )

    def test_filter_is_immutable(self):
        condition = FilterCondition(
            column="name",
            operator=FilterOperator.EQ,
            value="John"
        )
        with pytest.raises(AttributeError):
            condition.column = "other"
        with pytest.raises(AttributeError):
            condition.value = "Jane"


class TestFilterConditionToQueryDict:
    def test_to_query_dict_contains_all_fields(self):
        condition = FilterCondition(
            column="name",
            operator=FilterOperator.EQ,
            value="John",
            case_sensitive=False
        )
        query_dict = condition.to_query_dict()

        assert "column" in query_dict
        assert "operator" in query_dict
        assert "value" in query_dict
        assert "case_sensitive" in query_dict

        assert query_dict["column"] == "name"
        assert query_dict["operator"] == "EQ"
        assert query_dict["value"] == "John"
        assert query_dict["case_sensitive"] is False

    def test_to_query_dict_returns_dict(self):
        condition = FilterCondition(
            column="age",
            operator=FilterOperator.GT,
            value=18
        )
        result = condition.to_query_dict()
        assert isinstance(result, dict)
