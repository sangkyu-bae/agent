"""excel_generator 도메인 정책 테스트 (excel-generator-node Design §3.2)."""
from src.domain.excel_generator.policies import (
    MAX_LLM_STRUCTURED_ROWS,
    MAX_SHEETS,
    parse_raw_index,
    validate_plan,
)
from src.domain.excel_generator.schemas import SheetPlanItem


def _llm_item(rows=None, columns=None, name="정리"):
    return SheetPlanItem(
        source="llm", sheet_name=name,
        columns=columns if columns is not None else ["a"],
        rows=rows if rows is not None else [["v"]],
    )


class TestParseRawIndex:
    def test_valid(self):
        assert parse_raw_index("raw:0") == 0
        assert parse_raw_index("raw:12") == 12

    def test_non_raw_returns_none(self):
        assert parse_raw_index("llm") is None
        assert parse_raw_index("raw:abc") is None
        assert parse_raw_index("") is None


class TestValidatePlan:
    def test_empty_plan_is_violation(self):
        assert validate_plan([], catalog_size=0) != []

    def test_valid_raw_and_llm_mix(self):
        items = [SheetPlanItem(source="raw:0", sheet_name="원본"), _llm_item()]
        assert validate_plan(items, catalog_size=1) == []

    def test_raw_index_out_of_range(self):
        items = [SheetPlanItem(source="raw:3", sheet_name="원본")]
        violations = validate_plan(items, catalog_size=1)
        assert any("raw" in v for v in violations)

    def test_unknown_source(self):
        items = [SheetPlanItem(source="magic", sheet_name="x")]
        assert validate_plan(items, catalog_size=0) != []

    def test_llm_item_without_columns_is_violation(self):
        items = [SheetPlanItem(source="llm", sheet_name="x")]
        assert validate_plan(items, catalog_size=0) != []

    def test_sheet_count_over_max_is_violation(self):
        items = [_llm_item(name=f"s{i}") for i in range(MAX_SHEETS + 1)]
        violations = validate_plan(items, catalog_size=0)
        assert any("시트 수" in v for v in violations)

    def test_llm_rows_over_cap_is_not_violation(self):
        # 행 상한 초과는 위반이 아니라 절단 대상 (Design §6.1 #4)
        items = [_llm_item(rows=[["v"]] * (MAX_LLM_STRUCTURED_ROWS + 50))]
        assert validate_plan(items, catalog_size=0) == []
