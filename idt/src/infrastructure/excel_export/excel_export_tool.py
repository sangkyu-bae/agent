"""LangChain Tool: Excel 파일 생성 도구.

Agent가 pandas로 Excel 파일을 생성하고 저장 경로를 반환하는 Tool.
"""
import os
import tempfile
import uuid
from typing import Any, Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.domain.excel_export.schemas import ExcelExportRequest, ExcelSheetData
from src.infrastructure.excel_export.pandas_excel_exporter import PandasExcelExporter
from src.infrastructure.logging import get_logger


class ExcelExportInput(BaseModel):
    """ExcelExportTool 입력 스키마."""

    columns: list[str] = Field(description="첫 번째 시트의 컬럼 헤더 목록")
    rows: list[list[Any]] = Field(description="첫 번째 시트의 데이터 행 목록")
    filename: str = Field(default="output.xlsx", description="저장할 파일명 (.xlsx 자동 추가)")
    sheet_name: str = Field(default="Sheet1", description="첫 번째 시트 이름")
    output_dir: str = Field(default="", description="저장 디렉토리 (기본값: 임시 디렉토리)")
    extra_sheets: Optional[list[dict[str, Any]]] = Field(
        default=None,
        description="추가 시트 목록. 각 항목: {sheet_name, columns, rows}",
    )


class ExcelExportTool(BaseTool):
    """LangChain 호환 Excel 파일 생성 Tool.

    pandas + openpyxl을 사용해 Excel 파일을 생성하고 저장 경로를 반환한다.
    """

    name: str = "excel_export"
    description: str = (
        "Generate an Excel (.xlsx) file from tabular data and save it to disk. "
        "Provide columns (list of header names) and rows (list of data rows). "
        "Returns the absolute path to the saved file. "
        "Use this when you need to export data as an Excel spreadsheet."
    )
    args_schema: type = ExcelExportInput

    def _run(
        self,
        columns: list[str],
        rows: list[list[Any]],
        filename: str = "output.xlsx",
        sheet_name: str = "Sheet1",
        output_dir: str = "",
        extra_sheets: Optional[list[dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> str:
        logger = get_logger(__name__)
        request_id = str(uuid.uuid4())

        logger.info(
            "Excel export tool started",
            request_id=request_id,
            output_filename=filename,
            sheet_name=sheet_name,
            row_count=len(rows),
        )

        try:
            sheets = [ExcelSheetData(sheet_name=sheet_name, columns=columns, rows=rows)]

            if extra_sheets:
                for s in extra_sheets:
                    sheets.append(
                        ExcelSheetData(
                            sheet_name=s.get("sheet_name", "Sheet"),
                            columns=s["columns"],
                            rows=s.get("rows", []),
                        )
                    )

            request = ExcelExportRequest(
                filename=filename,
                sheets=sheets,
                request_id=request_id,
                user_id="tool",
            )

            exporter = PandasExcelExporter()
            result = exporter.export(request)

            save_dir = output_dir if output_dir else tempfile.gettempdir()
            os.makedirs(save_dir, exist_ok=True)
            file_path = os.path.join(save_dir, result.filename)

            with open(file_path, "wb") as f:
                f.write(result.excel_bytes)

            logger.info(
                "Excel export tool completed",
                request_id=request_id,
                file_path=file_path,
                size_bytes=result.size_bytes,
            )

            return file_path

        except Exception as exc:
            logger.error(
                "Excel export tool failed",
                exception=exc,
                request_id=request_id,
                output_filename=filename,
            )
            return f"ERROR: Excel 생성 실패 - {exc}"

    async def _arun(
        self,
        columns: list[str],
        rows: list[list[Any]],
        filename: str = "output.xlsx",
        sheet_name: str = "Sheet1",
        output_dir: str = "",
        extra_sheets: Optional[list[dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> str:
        return self._run(
            columns=columns,
            rows=rows,
            filename=filename,
            sheet_name=sheet_name,
            output_dir=output_dir,
            extra_sheets=extra_sheets,
        )
