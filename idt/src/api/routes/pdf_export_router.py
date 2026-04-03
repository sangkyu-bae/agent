"""HTML → PDF 변환 API Router.

POST /api/v1/pdf/export
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel

from src.application.use_cases.html_to_pdf_use_case import HtmlToPdfUseCase
from src.domain.pdf_export.schemas import HtmlToPdfRequest

router = APIRouter(prefix="/api/v1/pdf", tags=["PDF Export"])


class PdfExportRequestBody(BaseModel):
    html_content: str
    filename: str = "output.pdf"
    user_id: str
    css_content: Optional[str] = None
    base_url: Optional[str] = None


def get_html_to_pdf_use_case() -> HtmlToPdfUseCase:
    """DI placeholder — create_app()에서 override 한다."""
    raise NotImplementedError("Override this dependency in create_app()")


@router.post("/export")
async def export_html_to_pdf(
    body: PdfExportRequestBody,
    use_case: HtmlToPdfUseCase = Depends(get_html_to_pdf_use_case),
) -> Response:
    """HTML 콘텐츠를 PDF 파일로 변환하여 반환한다.

    Args:
        body: html_content, filename, user_id, css_content (optional), base_url (optional)

    Returns:
        PDF 파일 (application/pdf)
    """
    request = HtmlToPdfRequest(
        html_content=body.html_content,
        filename=body.filename,
        request_id=str(uuid.uuid4()),
        user_id=body.user_id,
        css_content=body.css_content,
        base_url=body.base_url,
    )

    result = await use_case.convert(request)

    return Response(
        content=result.pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{result.filename}"',
            "Content-Length": str(result.size_bytes),
        },
    )
