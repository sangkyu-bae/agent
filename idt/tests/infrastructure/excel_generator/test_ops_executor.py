"""ops 실행기 테스트 (excel-generator-spec-ops Design §6.3, §8.3).

핵심 검증:
- 숫자 변환은 비교·정렬·집계 판단에만 쓰고, 결과 셀은 원천 값 그대로 (Design §6.3)
- 결과 행에 300행 상한 미적용 (Plan SC-1)
- groupby 집계가 pandas 기준값과 일치 (Plan SC-2)
"""
import pandas as pd
import pytest
from src.domain.excel_generator.policies import MAX_LLM_STRUCTURED_ROWS
from src.infrastructure.excel_generator import ops_executor
from src.infrastructure.excel_generator.ops_executor import apply_ops

COLS = ["고객명", "지점", "잔액", "연체일수"]
ROWS = [
    ["a", "강남", "1,200", 5],
    ["b", "강남", 800, 0],
    ["c", "서초", "2,500원", 12],
    ["d", "서초", "-", 3],
    ["e", None, 300, None],
]


def _run(ops, columns=COLS, rows=ROWS):
    return apply_ops(columns, rows, ops)


class TestFilter:
    def test_numeric_compare_on_mixed_strings(self):  # E1
        cols, rows, truncated = _run(
            [{"op": "filter", "col": "잔액", "cmp": ">", "value": 1000}]
        )
        assert cols == COLS
        assert rows == [ROWS[0], ROWS[2]]  # 원값 "1,200" / "2,500원" 유지
        assert truncated is False

    def test_unconvertible_rows_excluded(self):  # E2
        _, rows, _ = _run([{"op": "filter", "col": "잔액", "cmp": "<=", "value": 10000}])
        assert ["d", "서초", "-", 3] not in rows
        assert len(rows) == 4

    def test_eq_numeric_and_ne(self):  # E8
        _, eq_rows, _ = _run([{"op": "filter", "col": "잔액", "cmp": "==", "value": 800}])
        assert eq_rows == [ROWS[1]]
        _, ne_rows, _ = _run([{"op": "filter", "col": "잔액", "cmp": "!=", "value": 800}])
        assert ROWS[1] not in ne_rows
        assert ROWS[3] in ne_rows  # 변환 불가 셀은 != 에 포함

    def test_eq_string(self):
        _, rows, _ = _run([{"op": "filter", "col": "지점", "cmp": "==", "value": "서초"}])
        assert [r[0] for r in rows] == ["c", "d"]

    def test_in_and_contains(self):  # E8
        _, in_rows, _ = _run(
            [{"op": "filter", "col": "고객명", "cmp": "in", "value": ["a", "e"]}]
        )
        assert [r[0] for r in in_rows] == ["a", "e"]
        _, c_rows, _ = _run([{"op": "filter", "col": "지점", "cmp": "contains", "value": "강"}])
        assert [r[0] for r in c_rows] == ["a", "b"]

    def test_in_matches_numbers_by_value_or_text(self):
        _, rows, _ = _run([{"op": "filter", "col": "연체일수", "cmp": "in", "value": ["5", 12]}])
        assert [r[0] for r in rows] == ["a", "c"]

    def test_date_compare(self):  # E7
        cols = ["건", "기준일"]
        rows = [["x", "2025-12-31"], ["y", "2026.01.15"], ["z", "미정"]]
        _, out, _ = apply_ops(
            cols, rows, [{"op": "filter", "col": "기준일", "cmp": ">=", "value": "2026-01-01"}]
        )
        assert out == [["y", "2026.01.15"]]

    def test_string_order_compare_when_value_not_number_or_date(self):
        _, rows, _ = _run([{"op": "filter", "col": "고객명", "cmp": ">", "value": "c"}])
        assert [r[0] for r in rows] == ["d", "e"]

    def test_multiple_filters_are_and(self):
        _, rows, _ = _run([
            {"op": "filter", "col": "지점", "cmp": "==", "value": "강남"},
            {"op": "filter", "col": "연체일수", "cmp": ">", "value": 0},
        ])
        assert [r[0] for r in rows] == ["a"]


class TestSortTopSelect:
    def test_multi_key_sort(self):  # E3
        _, rows, _ = _run([{"op": "sort", "by": [
            {"col": "지점", "desc": True}, {"col": "연체일수"},
        ]}])
        # 지점 desc(서초>강남), null 뒤 / 같은 지점 안에서는 연체일수 asc
        assert [r[0] for r in rows] == ["d", "c", "b", "a", "e"]

    def test_numeric_sort_on_numeric_strings(self):
        _, rows, _ = _run([
            {"op": "filter", "col": "잔액", "cmp": ">=", "value": 0},
            {"op": "sort", "by": [{"col": "잔액", "desc": True}]},
        ])
        assert [r[0] for r in rows] == ["c", "a", "b", "e"]

    def test_mixed_column_sorts_as_text_nulls_last(self):  # E4
        cols = ["k"]
        rows = [["b"], [None], [10], ["a"]]
        _, out, _ = apply_ops(cols, rows, [{"op": "sort", "by": [{"col": "k"}]}])
        assert out == [[10], ["a"], ["b"], [None]]

    def test_top_and_select(self):
        cols, rows, _ = _run([
            {"op": "sort", "by": [{"col": "연체일수", "desc": True}]},
            {"op": "top", "n": 2},
            {"op": "select", "columns": ["연체일수", "고객명"]},
        ])
        assert cols == ["연체일수", "고객명"]
        assert rows == [[12, "c"], [5, "a"]]


class TestGroupby:
    def test_aggregates_match_pandas(self):  # E5
        cols = ["지점", "잔액"]
        rows = [["강남", 100], ["강남", "200"], ["서초", 50], ["서초", "x"], ["강남", None]]
        out_cols, out, _ = apply_ops(cols, rows, [{"op": "groupby", "by": ["지점"], "agg": [
            {"col": "잔액", "fn": "sum", "as": "합계"},
            {"col": "잔액", "fn": "mean"},
            {"col": "잔액", "fn": "count", "as": "건수"},
            {"col": "잔액", "fn": "min"},
            {"col": "잔액", "fn": "max"},
        ]}])
        assert out_cols == ["지점", "합계", "잔액_mean", "건수", "잔액_min", "잔액_max"]
        by = {r[0]: r for r in out}
        assert by["강남"][1:] == [300.0, 150.0, 2, 100.0, 200.0]
        # count는 non-null 개수 (변환 불가 "x"도 값이 있으므로 포함)
        assert by["서초"][1:] == [50.0, 50.0, 2, 50.0, 50.0]

    def test_null_group_kept(self):
        _, out, _ = _run([{"op": "groupby", "by": ["지점"], "agg": [
            {"col": "고객명", "fn": "count", "as": "건수"}]}])
        assert sorted((r[0] or "", r[1]) for r in out) == [("", 1), ("강남", 2), ("서초", 2)]

    def test_matches_pandas_reference_on_numeric_data(self):
        cols = ["g", "v"]
        rows = [[i % 3, i * 1.5] for i in range(30)]
        _, out, _ = apply_ops(cols, rows, [{"op": "groupby", "by": ["g"], "agg": [
            {"col": "v", "fn": "sum", "as": "s"}]}])
        ref = pd.DataFrame(rows, columns=cols).groupby("g")["v"].sum().to_dict()
        assert {r[0]: r[1] for r in out} == ref

    def test_sort_after_groupby(self):
        _, out, _ = _run([
            {"op": "groupby", "by": ["지점"], "agg": [{"col": "연체일수", "fn": "sum", "as": "s"}]},
            {"op": "sort", "by": [{"col": "s", "desc": True}]},
        ])
        assert out[0][0] == "서초"


class TestCapsAndOutput:
    def test_result_not_capped_at_llm_limit(self):  # E6
        cols = ["i", "v"]
        rows = [[i, i % 2] for i in range(1000)]
        _, out, truncated = apply_ops(cols, rows, [{"op": "filter", "col": "v", "cmp": "==", "value": 0}])
        assert len(out) == 500 > MAX_LLM_STRUCTURED_ROWS
        assert truncated is False

    def test_excel_row_limit_truncates(self, monkeypatch):
        monkeypatch.setattr(ops_executor, "EXCEL_MAX_DATA_ROWS", 3)
        _, out, truncated = apply_ops(["i"], [[i] for i in range(5)], [])
        assert out == [[0], [1], [2]]
        assert truncated is True

    def test_output_has_no_nan(self):
        _, out, _ = _run([{"op": "sort", "by": [{"col": "연체일수"}]}])
        assert ["e", None, 300, None] in out

    def test_input_rows_not_mutated(self):
        rows = [list(r) for r in ROWS]
        _run([{"op": "sort", "by": [{"col": "잔액"}]}, {"op": "top", "n": 1}], rows=rows)
        assert rows == ROWS

    def test_unknown_op_raises(self):
        # 검증을 통과한 명세만 들어오지만, 방어적으로 ValueError
        with pytest.raises(ValueError):
            _run([{"op": "eval"}])


class TestAct1:
    """Check I-1·M-1·M-5 (analysis §3)."""

    def test_in_matches_float_cells_with_int_values(self):  # I-1
        _, rows, _ = apply_ops(
            ["k"], [[5.0], [12.0], [3.0], [None]],
            [{"op": "filter", "col": "k", "cmp": "in", "value": [5, 12]}],
        )
        assert rows == [[5.0], [12.0]]

    def test_in_with_text_values_keeps_leading_zero_codes(self):  # M-1
        _, rows, _ = apply_ops(
            ["code"], [["001"], ["1"], ["01"]],
            [{"op": "filter", "col": "code", "cmp": "in", "value": ["001"]}],
        )
        assert rows == [["001"]]

    def test_eq_text_value_is_text_compare(self):  # M-1
        _, rows, _ = apply_ops(
            ["code"], [["001"], ["1"], [1]],
            [{"op": "filter", "col": "code", "cmp": "==", "value": "001"}],
        )
        assert rows == [["001"]]

    def test_eq_number_value_is_numeric_compare(self):
        _, rows, _ = apply_ops(
            ["code"], [["001"], ["1"], [1.0], ["x"]],
            [{"op": "filter", "col": "code", "cmp": "==", "value": 1}],
        )
        assert [r[0] for r in rows] == ["001", "1", 1.0]

    def test_range_with_numeric_string_value_is_numeric(self):  # M-1
        _, rows, _ = apply_ops(
            ["v"], [["999"], ["1,000"], [2000]],
            [{"op": "filter", "col": "v", "cmp": ">=", "value": "1000"}],
        )
        assert rows == [["1,000"], [2000]]

    def test_groupby_sum_without_numbers_is_none(self):  # M-5
        _, rows, _ = apply_ops(
            ["g", "v"], [["a", "x"], ["a", None], ["b", 3]],
            [{"op": "groupby", "by": ["g"], "agg": [{"col": "v", "fn": "sum", "as": "s"}]}],
        )
        assert {r[0]: r[1] for r in rows} == {"a": None, "b": 3.0}
