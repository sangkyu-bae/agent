"""StyledExcelExporter 테스트 (excel-generator-spec-ops Design §3.3, §8.4).

핵심 검증:
- column_types 없는 요청은 PandasExcelExporter와 같은 값·구성, 서식 없음 (Plan SC-4)
- column_types 시트는 값 변환 + number_format + 틀 고정·자동 필터·헤더 서식 (Plan SC-3)
- 서식 실패는 값만 기록하고 warning (Design §6.1 #7)
"""
import datetime
import io
from unittest.mock import MagicMock

from openpyxl import load_workbook
from src.domain.excel_export.schemas import ExcelExportRequest, ExcelSheetData
from src.infrastructure.excel.preview_reader import ExcelPreviewReader
from src.infrastructure.excel_export import styled_excel_exporter
from src.infrastructure.excel_export.pandas_excel_exporter import PandasExcelExporter
from src.infrastructure.excel_export.styled_excel_exporter import StyledExcelExporter


def _request(*sheets: ExcelSheetData) -> ExcelExportRequest:
    return ExcelExportRequest(
        filename="out.xlsx", sheets=list(sheets), request_id="req-1", user_id="u",
    )


def _typed_sheet() -> ExcelSheetData:
    return ExcelSheetData(
        sheet_name="연체",
        columns=["고객명", "잔액", "비율", "기준일", "메모"],
        rows=[
            ["가나다라마바사아자차카타파하 주식회사", "1,234원", "12.5%", "2026.11.19", "N/A"],
            ["b", 500, 0.3, "2026-01-02", "x"],
        ],
        column_types={
            "잔액": "currency", "비율": "percent", "기준일": "date", "메모": "number",
        },
    )


def _workbook(exporter: StyledExcelExporter, request: ExcelExportRequest):
    result = exporter.export(request)
    return result, load_workbook(io.BytesIO(result.excel_bytes))


def _values(ws) -> list[tuple]:
    return list(ws.iter_rows(values_only=True))


class TestWithoutColumnTypes:
    def test_same_values_as_pandas_exporter(self):  # X1
        sheets = [
            ExcelSheetData(sheet_name="A", columns=["n", "v"], rows=[["x", 1], ["y", None]]),
            ExcelSheetData(sheet_name="B", columns=["k"], rows=[["1,234"]]),
        ]
        _, styled = _workbook(StyledExcelExporter(MagicMock()), _request(*sheets))
        plain = load_workbook(io.BytesIO(PandasExcelExporter().export(_request(*sheets)).excel_bytes))
        assert styled.sheetnames == plain.sheetnames
        for name in styled.sheetnames:
            assert _values(styled[name]) == _values(plain[name])
            assert styled[name].freeze_panes is None
            assert styled[name].auto_filter.ref is None

    def test_result_metadata(self):
        result, _ = _workbook(
            StyledExcelExporter(MagicMock()),
            _request(ExcelSheetData(columns=["a"], rows=[[1]])),
        )
        assert result.sheet_count == 1
        assert result.size_bytes == len(result.excel_bytes)
        assert result.exporter_used == "styled+openpyxl"


class TestWithColumnTypes:
    def test_currency_converted_and_formatted(self):  # X2
        _, wb = _workbook(StyledExcelExporter(MagicMock()), _request(_typed_sheet()))
        ws = wb["연체"]
        assert ws["B2"].value == 1234
        assert ws["B3"].value == 500
        assert ws["B2"].number_format == "#,##0"

    def test_percent_and_date(self):  # X3
        _, wb = _workbook(StyledExcelExporter(MagicMock()), _request(_typed_sheet()))
        ws = wb["연체"]
        assert ws["C2"].value == 0.125
        assert ws["C2"].number_format == "0.0%"
        assert ws["D2"].value == datetime.datetime(2026, 11, 19)
        assert ws["D2"].number_format == "yyyy-mm-dd"

    def test_unconvertible_kept_as_original(self):
        _, wb = _workbook(StyledExcelExporter(MagicMock()), _request(_typed_sheet()))
        assert wb["연체"]["E2"].value == "N/A"

    def test_table_format(self):  # X4
        _, wb = _workbook(StyledExcelExporter(MagicMock()), _request(_typed_sheet()))
        ws = wb["연체"]
        assert ws.freeze_panes == "A2"
        assert ws.auto_filter.ref == "A1:E3"
        assert ws["A1"].font.bold is True

    def test_column_width(self):  # X5
        _, wb = _workbook(StyledExcelExporter(MagicMock()), _request(_typed_sheet()))
        ws = wb["연체"]
        long_width = ws.column_dimensions["A"].width
        short_width = ws.column_dimensions["C"].width
        assert long_width > short_width
        assert long_width <= 50

    def test_only_typed_sheet_formatted(self):
        plain = ExcelSheetData(sheet_name="plain", columns=["a"], rows=[["1,234"]])
        _, wb = _workbook(StyledExcelExporter(MagicMock()), _request(_typed_sheet(), plain))
        assert wb["plain"].freeze_panes is None
        assert wb["plain"]["A2"].value == "1,234"


class TestFailures:
    def test_format_failure_keeps_values_and_warns(self, monkeypatch):  # X6
        def _boom(*args, **kwargs):
            raise ValueError("format boom")

        monkeypatch.setattr(styled_excel_exporter, "_apply_table_format", _boom)
        logger = MagicMock()
        _, wb = _workbook(StyledExcelExporter(logger), _request(_typed_sheet()))
        assert wb["연체"]["B2"].value == 1234  # 값 변환은 유지
        assert wb["연체"].freeze_panes is None
        logger.warning.assert_called_once()
        assert logger.warning.call_args.kwargs["request_id"] == "req-1"
        assert isinstance(logger.warning.call_args.kwargs["exception"], ValueError)


class TestPreviewCompatibility:
    def test_preview_reader_reads_styled_file(self, tmp_path):  # X7
        result = StyledExcelExporter(MagicMock()).export(_request(_typed_sheet()))
        path = tmp_path / "out.xlsx"
        path.write_bytes(result.excel_bytes)
        sheets = ExcelPreviewReader().read(str(path), max_rows=10, max_cols=10)
        assert sheets[0].columns == ["고객명", "잔액", "비율", "기준일", "메모"]
        assert sheets[0].rows[0][1] == "1234"
        assert sheets[0].rows[0][3].startswith("2026-11-19")
