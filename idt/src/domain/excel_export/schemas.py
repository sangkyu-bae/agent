"""Domain schemas for Excel export module.

No external API calls, no LangChain, no pandas in domain layer.
"""
from typing import Any

from pydantic import BaseModel, field_validator


class ExcelSheetData(BaseModel):
    """단일 시트 데이터."""

    sheet_name: str = "Sheet1"
    columns: list[str]
    rows: list[list[Any]] = []

    @field_validator("columns")
    @classmethod
    def columns_must_not_be_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("columns must not be empty")
        return v

    @field_validator("sheet_name")
    @classmethod
    def sheet_name_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("sheet_name must not be empty")
        return v


class ExcelExportRequest(BaseModel):
    """Excel 파일 생성 요청."""

    filename: str
    sheets: list[ExcelSheetData]
    request_id: str
    user_id: str

    @field_validator("filename")
    @classmethod
    def filename_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("filename must not be empty")
        if not v.endswith(".xlsx"):
            return v + ".xlsx"
        return v

    @field_validator("sheets")
    @classmethod
    def sheets_must_not_be_empty(cls, v: list[ExcelSheetData]) -> list[ExcelSheetData]:
        if not v:
            raise ValueError("sheets must have at least one sheet")
        return v


class ExcelExportResult(BaseModel):
    """Excel 파일 생성 결과."""

    filename: str
    user_id: str
    request_id: str
    excel_bytes: bytes
    size_bytes: int
    sheet_count: int
    exporter_used: str
