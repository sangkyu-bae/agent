"""document_extractor 라우터 (document-template-extractor Design §3-1).

- POST /api/v1/document-extractor/extract : 업로드 → HTML + 슬롯 추천 (stateless)
- POST /api/v1/document-extractor/refine  : 재추천 (상한 R5)
- GET  /api/v1/document-extractor/files/{file_id} : 런타임 산출 파일 다운로드 (owner-only)

DI placeholder는 lifespan에서 override (main.py). 저장은 기존 POST /agents 재사용.
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from src.application.document_extractor.extract_use_case import (
    ExtractDocumentUseCase,
)
from src.application.document_extractor.refine_use_case import RefineSlotsUseCase
from src.application.document_extractor.schemas import (
    ExtractResponse,
    RefineRequest,
    RefineResponse,
)
from src.domain.auth.entities import User
from src.domain.document_extractor.exceptions import (
    DocumentTooLargeError,
    InvalidDocumentError,
    McpConversionError,
    McpToolNotConfiguredError,
    RegenLimitExceededError,
    SlotExtractionFailedError,
)
from src.interfaces.dependencies.auth import get_current_user

router = APIRouter(prefix="/api/v1/document-extractor", tags=["document-extractor"])


def get_extract_document_use_case() -> ExtractDocumentUseCase:
    raise NotImplementedError("ExtractDocumentUseCase not initialized")


def get_refine_slots_use_case() -> RefineSlotsUseCase:
    raise NotImplementedError("RefineSlotsUseCase not initialized")


def get_document_attachment_store():
    raise NotImplementedError("AgentAttachmentStore not initialized")


def _http_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message}
    )


@router.post("/extract", response_model=ExtractResponse)
async def extract_document(
    file: UploadFile = File(...),
    mcp_pdf_to_html_tool_id: str | None = Form(None),
    mcp_html_to_doc_tool_id: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    use_case: ExtractDocumentUseCase = Depends(get_extract_document_use_case),
) -> ExtractResponse:
    """PDF/Word 업로드 → MCP 변환 → 자동화 슬롯 추천 (GA2, compiler 무관).

    Errors:
        400 INVALID_DOCUMENT / MCP_TOOL_NOT_CONFIGURED
        413 DOCUMENT_TOO_LARGE
        502 MCP_CONVERSION_FAILED / SLOT_EXTRACTION_FAILED
    """
    import uuid

    request_id = str(uuid.uuid4())
    file_bytes = await file.read()
    try:
        return await use_case.execute(
            file_bytes=file_bytes,
            filename=file.filename or "unknown",
            owner_user_id=str(current_user.id),
            mcp_pdf_to_html_tool_id=mcp_pdf_to_html_tool_id,
            mcp_html_to_doc_tool_id=mcp_html_to_doc_tool_id,
            request_id=request_id,
        )
    except InvalidDocumentError as e:
        raise _http_error(400, "INVALID_DOCUMENT", str(e))
    except DocumentTooLargeError as e:
        raise _http_error(413, "DOCUMENT_TOO_LARGE", str(e))
    except McpToolNotConfiguredError as e:
        raise _http_error(400, "MCP_TOOL_NOT_CONFIGURED", str(e))
    except McpConversionError as e:
        raise _http_error(502, "MCP_CONVERSION_FAILED", str(e))
    except SlotExtractionFailedError as e:
        raise _http_error(502, "SLOT_EXTRACTION_FAILED", str(e))


@router.post("/refine", response_model=RefineResponse)
async def refine_slots(
    body: RefineRequest,
    current_user: User = Depends(get_current_user),
    use_case: RefineSlotsUseCase = Depends(get_refine_slots_use_case),
) -> RefineResponse:
    """슬롯 재추천 — 거절/보강 및 유휴 5분 재생성 (GA3).

    Errors:
        429 REGEN_LIMIT_EXCEEDED
        502 SLOT_EXTRACTION_FAILED
    """
    import uuid

    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(
            html=body.html,
            instruction=body.instruction,
            prev_slots=body.prev_slots,
            regen_count=body.regen_count,
            request_id=request_id,
        )
    except RegenLimitExceededError as e:
        raise _http_error(429, "REGEN_LIMIT_EXCEEDED", str(e))
    except SlotExtractionFailedError as e:
        raise _http_error(502, "SLOT_EXTRACTION_FAILED", str(e))


_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
}


@router.get("/files/{file_id}")
async def download_generated_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    store=Depends(get_document_attachment_store),
) -> FileResponse:
    """런타임 산출 문서 다운로드 (GB3). uploader==viewer 재사용 (D3).

    Errors:
        404 FILE_NOT_FOUND, 403 FORBIDDEN
    """
    stored = store.load(file_id)
    if stored is None:
        raise _http_error(404, "FILE_NOT_FOUND", "파일을 찾을 수 없거나 만료되었습니다.")
    if stored.owner_user_id != str(current_user.id):
        raise _http_error(403, "FORBIDDEN", "본인이 생성한 파일만 다운로드할 수 있습니다.")

    ext = "." + stored.filename.rsplit(".", 1)[-1].lower() if "." in stored.filename else ""
    return FileResponse(
        path=stored.file_path,
        filename=stored.filename,
        media_type=_MEDIA_TYPES.get(ext, "application/octet-stream"),
    )
