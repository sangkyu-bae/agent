"""excel-preview 응답 스키마 (Design §3.1).

프론트 ExcelPreviewResponse(idt_front/src/types/excelPreview.ts)와 필드 동일
— API 계약 동기화 규칙 4-1 (FR-14).
"""
from pydantic import BaseModel

from src.domain.excel_preview.value_objects import ExcelSheetData


class ExcelPreviewSheet(BaseModel):
    name: str              # 시트 이름
    columns: list[str]     # 첫 행(헤더). 빈 셀 "". 행 0개면 []
    rows: list[list[str]]  # 2행째부터 상한까지. 모든 셀 문자열
    total_rows: int        # 전체 행 수 (Design §3.4 산출 규칙)
    total_cols: int        # 전체 열 수
    truncated: bool        # 행/열이 상한에 걸려 잘렸는가

    @classmethod
    def from_domain(cls, data: ExcelSheetData) -> "ExcelPreviewSheet":
        return cls(
            name=data.name, columns=data.columns, rows=data.rows,
            total_rows=data.total_rows, total_cols=data.total_cols,
            truncated=data.truncated,
        )


class ExcelPreviewResponse(BaseModel):
    file_id: str
    filename: str
    max_rows: int                    # 적용된 행 상한 (config)
    max_cols: int                    # 적용된 열 상한 (config)
    sheets: list[ExcelPreviewSheet]  # 통합문서 순서, 모든 시트(빈 시트 포함)
