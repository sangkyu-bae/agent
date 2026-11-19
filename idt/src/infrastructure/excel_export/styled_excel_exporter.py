"""서식 적용 Excel 생성기 (excel-generator-spec-ops Design §3.3, §2.1).

엑셀 생성 노드 전용. column_types가 있는 시트만 값 변환과 표 서식을 적용하고,
없는 시트는 PandasExcelExporter와 같은 방식으로 값만 기록한다 (Plan SC-4).
공용 PandasExcelExporter(REST·ExcelExportTool 경로)는 건드리지 않는다.
"""
import datetime
import io
import unicodedata
from typing import Any

import pandas as pd
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from src.domain.excel_export.interfaces import ExcelExporterInterface
from src.domain.excel_export.schemas import (
    ExcelExportRequest,
    ExcelExportResult,
    ExcelSheetData,
)
from src.domain.excel_generator.spec_policies import NUMBER_FORMATS, coerce_cell
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_HEADER_FONT = Font(bold=True)
_HEADER_FILL = PatternFill(fill_type="solid", start_color="F2F2F2", end_color="F2F2F2")
_MAX_COLUMN_WIDTH = 50
_MIN_COLUMN_WIDTH = 8
_WIDTH_SAMPLE_ROWS = 200  # 열 너비 계산에 쓰는 앞쪽 행 수 (대용량 시트 비용 상한)


class StyledExcelExporter(ExcelExporterInterface):
    """column_types 시트에 값 변환·number_format·표 서식을 적용하는 생성기."""

    def __init__(self, logger: LoggerInterface) -> None:
        self._logger = logger

    def export(self, request: ExcelExportRequest) -> ExcelExportResult:
        try:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                for sheet in request.sheets:
                    self._write_sheet(writer, sheet, request.request_id)
            excel_bytes = output.getvalue()
        except Exception as exc:
            raise RuntimeError(f"Excel 생성 중 오류가 발생했습니다: {exc}") from exc
        return ExcelExportResult(
            filename=request.filename,
            user_id=request.user_id,
            request_id=request.request_id,
            excel_bytes=excel_bytes,
            size_bytes=len(excel_bytes),
            sheet_count=len(request.sheets),
            exporter_used=self.get_exporter_name(),
        )

    def get_exporter_name(self) -> str:
        return "styled+openpyxl"

    def _write_sheet(self, writer, sheet: ExcelSheetData, request_id: str) -> None:
        types = sheet.column_types or {}
        rows = _coerce_rows(sheet.columns, sheet.rows, types) if types else sheet.rows
        df = pd.DataFrame(rows, columns=sheet.columns)
        df.to_excel(writer, sheet_name=sheet.sheet_name, index=False)
        if not types:
            return
        try:
            _apply_table_format(
                writer.sheets[sheet.sheet_name], sheet.columns, rows, types
            )
        except Exception as e:  # noqa: BLE001 — Design §6.1 #7: 서식 실패는 값만 기록
            self._logger.warning(
                "StyledExcelExporter format skipped",
                request_id=request_id,
                sheet_name=sheet.sheet_name,
                exception=e,
            )


def _coerce_rows(
    columns: list[str], rows: list[list[Any]], types: dict[str, str],
) -> list[list[Any]]:
    """의미 타입 컬럼만 coerce_cell로 변환 (실패 셀은 원값, Design §3.3)."""
    col_types = [types.get(c) for c in columns]
    return [
        [v if t is None else coerce_cell(v, t) for v, t in zip(row, col_types)]
        for row in rows
    ]


def _apply_table_format(
    ws, columns: list[str], rows: list[list[Any]], types: dict[str, str],
) -> None:
    """헤더 서식·number_format·열 너비·틀 고정·자동 필터 (Plan SC-3)."""
    last_row = len(rows) + 1
    for idx, column in enumerate(columns, start=1):
        header = ws.cell(row=1, column=idx)
        header.font = _HEADER_FONT
        header.fill = _HEADER_FILL
        _apply_number_format(ws, idx, last_row, types.get(column))
        letter = get_column_letter(idx)
        ws.column_dimensions[letter].width = _column_width(column, rows, idx - 1)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{last_row}"


def _apply_number_format(
    ws, col_idx: int, last_row: int, semantic_type: str | None,
) -> None:
    number_format = NUMBER_FORMATS.get(semantic_type or "text", "General")
    if number_format == "General":
        return
    for (cell,) in ws.iter_rows(
        min_row=2, max_row=last_row, min_col=col_idx, max_col=col_idx
    ):
        cell.number_format = number_format


def _column_width(header: str, rows: list[list[Any]], pos: int) -> float:
    widths = [_display_width(header)]
    widths.extend(
        _display_width(row[pos]) for row in rows[:_WIDTH_SAMPLE_ROWS] if pos < len(row)
    )
    return float(min(max(max(widths) + 2, _MIN_COLUMN_WIDTH), _MAX_COLUMN_WIDTH))


def _display_width(value: Any) -> int:
    """화면 폭 근사 — 한글 등 전각 문자는 2칸, 날짜는 yyyy-mm-dd 10칸."""
    if value is None:
        return 0
    if isinstance(value, (datetime.date, datetime.datetime)):
        return 10
    return sum(
        2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        for ch in str(value)
    )
