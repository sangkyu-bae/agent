"""excel_generator 도메인 스키마 테스트 (excel-generator-node Design §3.1)."""
from src.domain.excel_generator.schemas import (
    ExcelGenerateResult,
    RawSourceRef,
    SheetPlanItem,
)


class TestRawSourceRef:
    def test_fields(self):
        ref = RawSourceRef(
            catalog_idx=0, origin="analysis_worker",
            sheet_name="Sheet1", columns=["a", "b"], row_count=100,
        )
        assert ref.catalog_idx == 0
        assert ref.origin == "analysis_worker"
        assert ref.row_count == 100


class TestSheetPlanItem:
    def test_raw_item_defaults(self):
        item = SheetPlanItem(source="raw:0", sheet_name="원본")
        assert item.columns is None
        assert item.rows is None

    def test_llm_item(self):
        item = SheetPlanItem(
            source="llm", sheet_name="정리",
            columns=["이름"], rows=[["홍길동"]],
        )
        assert item.columns == ["이름"]
        assert item.rows == [["홍길동"]]


class TestExcelGenerateResult:
    def test_fields(self):
        result = ExcelGenerateResult(
            file_id="f" * 32, filename="output.xlsx",
            sheet_count=2, total_rows=10,
            truncated=False, used_raw_source=True,
        )
        assert result.filename == "output.xlsx"
        assert result.used_raw_source is True


class TestSpecFields:
    """excel-generator-spec-ops Design §3.4 — 선택 필드, 기본값 None/빈 dict."""

    def test_raw_source_ref_dtypes_default_empty(self):
        ref = RawSourceRef(
            catalog_idx=0, origin="o", sheet_name="s", columns=["a"], row_count=1,
        )
        assert ref.column_dtypes == {}

    def test_raw_source_ref_dtypes(self):
        ref = RawSourceRef(
            catalog_idx=0, origin="o", sheet_name="s", columns=["a"],
            row_count=1, column_dtypes={"a": "int64"},
        )
        assert ref.column_dtypes == {"a": "int64"}

    def test_sheet_plan_item_spec_defaults(self):
        item = SheetPlanItem(source="raw:0", sheet_name="원본")
        assert item.ops is None
        assert item.column_types is None

    def test_sheet_plan_item_spec_fields(self):
        item = SheetPlanItem(
            source="raw:0", sheet_name="상위",
            ops=[{"op": "top", "n": 3}], column_types={"a": "integer"},
        )
        assert item.ops == [{"op": "top", "n": 3}]
        assert item.column_types == {"a": "integer"}
