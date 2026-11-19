"""엑셀 시트 명세 정책 테스트 (excel-generator-spec-ops Design §3.2~§3.5, §8.2).

ops 검증은 연산 순서대로 컬럼 집합을 추적한다 — select로 빠진 컬럼은 이후 참조 불가,
groupby 결과 컬럼은 이후 참조 가능. 셀 변환은 실패 시 원값을 돌려준다.
"""
import datetime

from src.domain.excel_generator.spec_policies import (
    MAX_OPS_PER_SHEET,
    NUMBER_FORMATS,
    SEMANTIC_TYPES,
    agg_output_name,
    clean_numeric_text,
    coerce_cell,
    parse_date_text,
    validate_column_types,
    validate_ops,
)

COLS = ["고객명", "지점", "잔액", "연체일수"]


class TestValidateOpsBasics:
    def test_valid_chain_returns_no_violation(self):
        ops = [
            {"op": "filter", "col": "연체일수", "cmp": ">", "value": 0},
            {"op": "sort", "by": [{"col": "연체일수", "desc": True}]},
            {"op": "top", "n": 20},
            {"op": "select", "columns": ["고객명", "잔액"]},
        ]
        violations, result = validate_ops(ops, COLS)
        assert violations == []
        assert result == ["고객명", "잔액"]

    def test_unknown_op_is_violation(self):  # D1
        violations, _ = validate_ops([{"op": "eval", "expr": "1"}], COLS)
        assert any("eval" in v for v in violations)

    def test_non_dict_op_is_violation(self):
        violations, _ = validate_ops(["filter"], COLS)
        assert violations

    def test_ops_not_list_is_violation(self):
        violations, _ = validate_ops({"op": "top", "n": 1}, COLS)
        assert violations

    def test_too_many_ops_is_violation(self):  # D8
        ops = [{"op": "top", "n": 5}] * (MAX_OPS_PER_SHEET + 1)
        violations, _ = validate_ops(ops, COLS)
        assert any(str(MAX_OPS_PER_SHEET) in v for v in violations)


class TestValidateOpsColumns:
    def test_filter_unknown_column(self):  # D2
        violations, _ = validate_ops(
            [{"op": "filter", "col": "없는컬럼", "cmp": "==", "value": 1}], COLS
        )
        assert any("없는컬럼" in v for v in violations)

    def test_sort_on_column_removed_by_select(self):  # D3
        ops = [
            {"op": "select", "columns": ["고객명"]},
            {"op": "sort", "by": [{"col": "잔액"}]},
        ]
        violations, _ = validate_ops(ops, COLS)
        assert any("잔액" in v for v in violations)

    def test_select_unknown_column(self):
        violations, _ = validate_ops([{"op": "select", "columns": ["x"]}], COLS)
        assert violations

    def test_select_empty_columns(self):
        violations, _ = validate_ops([{"op": "select", "columns": []}], COLS)
        assert violations

    def test_sort_on_groupby_alias(self):  # D4
        ops = [
            {"op": "groupby", "by": ["지점"],
             "agg": [{"col": "잔액", "fn": "sum", "as": "잔액 합계"}]},
            {"op": "sort", "by": [{"col": "잔액 합계", "desc": True}]},
        ]
        violations, result = validate_ops(ops, COLS)
        assert violations == []
        assert result == ["지점", "잔액 합계"]

    def test_groupby_default_name(self):  # D5
        ops = [
            {"op": "groupby", "by": ["지점"], "agg": [{"col": "잔액", "fn": "sum"}]},
            {"op": "select", "columns": ["잔액_sum"]},
        ]
        violations, result = validate_ops(ops, COLS)
        assert violations == []
        assert result == ["잔액_sum"]

    def test_groupby_removes_non_key_columns(self):
        ops = [
            {"op": "groupby", "by": ["지점"], "agg": [{"col": "잔액", "fn": "sum"}]},
            {"op": "filter", "col": "고객명", "cmp": "==", "value": "a"},
        ]
        violations, _ = validate_ops(ops, COLS)
        assert any("고객명" in v for v in violations)


class TestValidateOpsFields:
    def test_top_invalid_n(self):  # D6
        for n in (0, -1, "5", None, True):
            violations, _ = validate_ops([{"op": "top", "n": n}], COLS)
            assert violations, n

    def test_in_requires_list_value(self):  # D7
        violations, _ = validate_ops(
            [{"op": "filter", "col": "지점", "cmp": "in", "value": "강남"}], COLS
        )
        assert violations

    def test_contains_requires_str_value(self):
        violations, _ = validate_ops(
            [{"op": "filter", "col": "지점", "cmp": "contains", "value": 1}], COLS
        )
        assert violations

    def test_unknown_cmp(self):
        violations, _ = validate_ops(
            [{"op": "filter", "col": "잔액", "cmp": "~=", "value": 1}], COLS
        )
        assert violations

    def test_sort_requires_entries(self):
        violations, _ = validate_ops([{"op": "sort", "by": []}], COLS)
        assert violations

    def test_unknown_agg_fn(self):
        violations, _ = validate_ops(
            [{"op": "groupby", "by": ["지점"], "agg": [{"col": "잔액", "fn": "median"}]}],
            COLS,
        )
        assert any("median" in v for v in violations)

    def test_groupby_requires_by_and_agg(self):
        assert validate_ops([{"op": "groupby", "by": [], "agg": [
            {"col": "잔액", "fn": "sum"}]}], COLS)[0]
        assert validate_ops([{"op": "groupby", "by": ["지점"], "agg": []}], COLS)[0]

    def test_groupby_duplicate_output_names(self):
        ops = [{"op": "groupby", "by": ["지점"], "agg": [
            {"col": "잔액", "fn": "sum", "as": "x"},
            {"col": "연체일수", "fn": "sum", "as": "x"},
        ]}]
        violations, _ = validate_ops(ops, COLS)
        assert violations


class TestAggOutputName:
    def test_alias_wins(self):
        assert agg_output_name({"col": "잔액", "fn": "sum", "as": "합계"}) == "합계"

    def test_default(self):
        assert agg_output_name({"col": "잔액", "fn": "mean"}) == "잔액_mean"

    def test_blank_alias_falls_back(self):
        assert agg_output_name({"col": "잔액", "fn": "sum", "as": " "}) == "잔액_sum"


class TestValidateColumnTypes:  # D10
    def test_valid(self):
        assert validate_column_types({"잔액": "currency", "연체일수": "integer"}, COLS) == []

    def test_unknown_type(self):
        violations = validate_column_types({"잔액": "money"}, COLS)
        assert any("money" in v for v in violations)

    def test_unknown_column(self):
        violations = validate_column_types({"없음": "text"}, COLS)
        assert any("없음" in v for v in violations)

    def test_not_dict(self):
        assert validate_column_types(["잔액"], COLS)

    def test_formats_cover_all_types(self):
        assert set(NUMBER_FORMATS) == set(SEMANTIC_TYPES)


class TestCleanNumericText:
    def test_variants(self):
        assert clean_numeric_text("1,234") == 1234.0
        assert clean_numeric_text(" ₩1,234 ") == 1234.0
        assert clean_numeric_text("1,234원") == 1234.0
        assert clean_numeric_text("$-5.5") == -5.5
        assert clean_numeric_text(12) == 12.0
        assert clean_numeric_text(1.5) == 1.5

    def test_failures(self):
        assert clean_numeric_text("N/A") is None
        assert clean_numeric_text("") is None
        assert clean_numeric_text(None) is None
        assert clean_numeric_text("(1,234)") is None
        assert clean_numeric_text(True) is None


class TestParseDateText:
    def test_variants(self):
        expected = datetime.datetime(2026, 11, 19)
        assert parse_date_text("2026-11-19") == expected
        assert parse_date_text("2026.11.19") == expected
        assert parse_date_text("2026/11/19") == expected
        assert parse_date_text("2026-11-19T10:30:00") == datetime.datetime(2026, 11, 19, 10, 30)

    def test_objects(self):
        assert parse_date_text(datetime.date(2026, 1, 2)) == datetime.datetime(2026, 1, 2)
        dt = datetime.datetime(2026, 1, 2, 3, 4)
        assert parse_date_text(dt) == dt

    def test_failures(self):
        assert parse_date_text("어제") is None
        assert parse_date_text("2026-13-01") is None
        assert parse_date_text(20261119) is None


class TestCoerceCell:
    def test_currency_and_integer(self):  # D11
        assert coerce_cell("1,234원", "currency") == 1234
        assert coerce_cell("₩-5", "integer") == -5
        assert isinstance(coerce_cell("1,234", "integer"), int)

    def test_integer_keeps_fraction(self):
        assert coerce_cell("1.5", "integer") == 1.5

    def test_number(self):
        assert coerce_cell("1,234.5", "number") == 1234.5

    def test_percent(self):  # D12
        assert coerce_cell("12.5%", "percent") == 0.125
        assert coerce_cell(0.3, "percent") == 0.3
        assert coerce_cell("0.3", "percent") == 0.3

    def test_date(self):  # D13
        assert coerce_cell("2026.11.19", "date") == datetime.datetime(2026, 11, 19)

    def test_failure_keeps_original(self):  # D14
        assert coerce_cell("N/A", "number") == "N/A"
        assert coerce_cell("어제", "date") == "어제"

    def test_text_unchanged(self):
        assert coerce_cell(123, "text") == 123
        assert coerce_cell("0012", "text") == "0012"

    def test_empty_becomes_none(self):
        assert coerce_cell("", "number") is None
        assert coerce_cell("  ", "date") is None
        assert coerce_cell(None, "currency") is None

    def test_unknown_type_unchanged(self):
        assert coerce_cell("1,234", "money") == "1,234"


class TestAct1Validation:
    """Check M-2·M-3·M-4 (analysis §3)."""

    def test_sort_desc_must_be_bool(self):  # M-2
        violations, _ = validate_ops(
            [{"op": "sort", "by": [{"col": "잔액", "desc": "false"}]}], COLS
        )
        assert any("desc" in v for v in violations)

    def test_sort_desc_optional(self):
        violations, _ = validate_ops([{"op": "sort", "by": [{"col": "잔액"}]}], COLS)
        assert violations == []

    def test_compare_requires_value(self):  # M-3
        for op in (
            {"op": "filter", "col": "잔액", "cmp": ">"},
            {"op": "filter", "col": "잔액", "cmp": "==", "value": None},
            {"op": "filter", "col": "잔액", "cmp": "!=", "value": None},
        ):
            violations, _ = validate_ops([op], COLS)
            assert any("value" in v for v in violations), op

    def test_select_duplicate_columns(self):  # M-4
        violations, _ = validate_ops(
            [{"op": "select", "columns": ["잔액", "잔액"]}], COLS
        )
        assert any("중복" in v for v in violations)
