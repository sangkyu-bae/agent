"""pandas Excel 파일 생성 API Router.

POST /api/v1/excel/export
"""
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel

from src.application.use_cases.excel_export_use_case import ExcelExportUseCase
from src.domain.excel_export.schemas import ExcelExportRequest, ExcelSheetData

router = APIRouter(prefix="/api/v1/excel", tags=["Excel Export"])


class SheetRequestBody(BaseModel):
    sheet_name: str = "Sheet1"
    columns: list[str]
    rows: list[list] = []


class ExcelExportRequestBody(BaseModel):
    filename: str = "output.xlsx"
    user_id: str
    sheets: list[SheetRequestBody]


def get_excel_export_use_case() -> ExcelExportUseCase:
    """DI placeholder — create_app()에서 override 한다."""
    raise NotImplementedError("Override this dependency in create_app()")


@router.post("/export")
async def export_excel(
    body: ExcelExportRequestBody,
    use_case: ExcelExportUseCase = Depends(get_excel_export_use_case),
) -> Response:
    """테이블 데이터를 Excel 파일로 변환하여 반환한다.

    Args:
        body: filename, user_id, sheets (sheet_name, columns, rows)

    Returns:
        Excel 파일 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
    """
    request = ExcelExportRequest(
        filename=body.filename,
        sheets=[
            ExcelSheetData(
                sheet_name=s.sheet_name,
                columns=s.columns,
                rows=s.rows,
            )
            for s in body.sheets
        ],
        request_id=str(uuid.uuid4()),
        user_id=body.user_id,
    )

    result = await use_case.export(request)

    return Response(
        content=result.excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{result.filename}"',
            "Content-Length": str(result.size_bytes),
        },
    )
