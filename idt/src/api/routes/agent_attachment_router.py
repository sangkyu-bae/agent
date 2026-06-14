"""Agent 첨부 업로드 엔드포인트 — POST /api/v1/agent/attachments.

ws-agent-excel-attachment Design §4.2:
- 엑셀(.xlsx/.xls)을 업로드해 file_id를 발급한다.
- 발급된 file_id를 `/ws/agent/{run_id}` subscribe 메시지의 attachments로 참조한다.
- owner_user_id는 Form이 아닌 인증 토큰(current_user)에서 취한다 (위변조 방지).

DI placeholder는 lifespan에서 override (main.py).
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from src.application.agent_attachment.upload_use_case import UploadAttachmentUseCase
from src.domain.agent_attachment.exceptions import (
    AttachmentTooLargeError,
    InvalidAttachmentError,
)
from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import get_current_user

router = APIRouter(prefix="/api/v1/agent", tags=["agent-attachment"])


def get_upload_attachment_use_case() -> UploadAttachmentUseCase:
    raise NotImplementedError("UploadAttachmentUseCase not initialized")


class AttachmentUploadResponse(BaseModel):
    file_id: str
    type: str
    filename: str
    size: int


@router.post(
    "/attachments",
    response_model=AttachmentUploadResponse,
    status_code=201,
)
async def upload_attachment(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    use_case: UploadAttachmentUseCase = Depends(get_upload_attachment_use_case),
) -> AttachmentUploadResponse:
    """엑셀 파일 업로드 → file_id 발급.

    Errors:
        400 INVALID_ATTACHMENT: 미허용 확장자/빈 파일
        413 ATTACHMENT_TOO_LARGE: 최대 크기 초과
        401: 인증 실패 (get_current_user)
    """
    file_bytes = await file.read()
    filename = file.filename or "unknown"

    try:
        stored = use_case.execute(
            file_bytes=file_bytes,
            filename=filename,
            owner_user_id=str(current_user.id),
        )
    except InvalidAttachmentError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_ATTACHMENT", "message": str(e)},
        )
    except AttachmentTooLargeError as e:
        raise HTTPException(
            status_code=413,
            detail={"code": "ATTACHMENT_TOO_LARGE", "message": str(e)},
        )

    return AttachmentUploadResponse(
        file_id=stored.file_id,
        type=stored.type.value,
        filename=stored.filename,
        size=stored.size,
    )
