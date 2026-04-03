"""Excel file upload API endpoint."""
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from src.application.use_cases.excel_upload_use_case import ExcelUploadUseCase
from src.domain.pipeline.schemas.excel_upload_schema import ExcelUploadResponse
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/excel", tags=["excel"])


def get_excel_upload_use_case() -> ExcelUploadUseCase:
    raise NotImplementedError("Configure excel upload use case dependency")


@router.post("/upload", response_model=ExcelUploadResponse)
async def upload_excel(
    file: UploadFile = File(...),
    user_id: str = Query(..., description="User ID for document ownership"),
    strategy_type: str = Query("full_token", description="Chunking strategy"),
    use_case: ExcelUploadUseCase = Depends(get_excel_upload_use_case),
) -> ExcelUploadResponse:
    """Upload an Excel file, chunk it, and store in vector store.

    Args:
        file: The Excel file (.xlsx or .xls).
        user_id: Owner of the document.
        strategy_type: Chunking strategy (full_token / parent_child / semantic).
        use_case: Injected ExcelUploadUseCase.

    Returns:
        ExcelUploadResponse with processing results.

    Raises:
        HTTPException 500: If processing fails.
    """
    request_id = str(uuid.uuid4())
    file_bytes = await file.read()
    filename = file.filename or "unknown.xlsx"

    result = await use_case.execute(
        file_bytes=file_bytes,
        filename=filename,
        user_id=user_id,
        request_id=request_id,
    )

    if result.status == "failed":
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Excel processing failed",
                "errors": result.errors,
            },
        )

    return result
