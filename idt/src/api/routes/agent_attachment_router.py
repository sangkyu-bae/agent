"""Agent 첨부 업로드 엔드포인트 — POST /api/v1/agent/attachments.

ws-agent-excel-attachment Design §4.2:
- 엑셀(.xlsx/.xls)을 업로드해 file_id를 발급한다.
- 발급된 file_id를 `/ws/agent/{run_id}` subscribe 메시지의 attachments로 참조한다.
- owner_user_id는 Form이 아닌 인증 토큰(current_user)에서 취한다 (위변조 방지).

DI placeholder는 lifespan에서 override (main.py).
"""
import asyncio

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from src.application.agent_attachment.upload_use_case import UploadAttachmentUseCase
from src.domain.agent_attachment.exceptions import (
    AttachmentTooLargeError,
    InvalidAttachmentError,
)
from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import get_current_user

from src.infrastructure.logging import get_logger

_logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/agent", tags=["agent-attachment"])


def get_upload_attachment_use_case() -> UploadAttachmentUseCase:
    raise NotImplementedError("UploadAttachmentUseCase not initialized")


class AttachmentUploadResponse(BaseModel):
    file_id: str
    type: str
    filename: str
    size: int
    # chat-image-attachment Design §4.2: 이미지일 때만 채워진다 (additive)
    width: int | None = None
    height: int | None = None


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
    """엑셀·이미지(png/jpg/webp) 업로드 → file_id 발급.

    Errors:
        400 INVALID_ATTACHMENT: 미허용 확장자/빈 파일
        413 ATTACHMENT_TOO_LARGE: 최대 크기 초과
        401: 인증 실패 (get_current_user)
    """
    file_bytes = await file.read()
    filename = file.filename or "unknown"

    try:
        # chat-image-attachment Design §7 (Analysis G-I1): PIL 리사이즈가 이벤트 루프를
        # 막지 않도록 스레드풀에서 실행한다 (엑셀은 I/O 만이라 영향 없음).
        stored = await asyncio.to_thread(
            use_case.execute,
            file_bytes=file_bytes,
            filename=filename,
            owner_user_id=str(current_user.id),
        )
    except InvalidAttachmentError as e:
        # Design §6.3 (Analysis G-M7): 손상·위장 파일은 원인을 로그에 남긴다 (바이트 없음)
        _logger.warning(
            "agent attachment rejected", exception=e,
            filename=filename, size=len(file_bytes), user_id=str(current_user.id),
        )
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
        width=stored.width,
        height=stored.height,
    )
