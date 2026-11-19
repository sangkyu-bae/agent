"""원문 뷰어 원본 파일 API (source-passage-viewer Design §4).

이 라우터는 source_viewer_di.wire_source_viewer() 가 킬스위치 on 일 때만 등록한다.
off 면 경로 자체가 없어 404 다. 비즈니스 로직은 GetOriginalUseCase 에 있다.
"""
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from src.application.source_viewer.get_original import GetOriginalUseCase
from src.domain.auth.entities import User
from src.domain.source_viewer.exceptions import (
    OriginalNotAvailableError,
    UnsupportedOriginalError,
)
from src.interfaces.dependencies.auth import get_current_user

router = APIRouter(prefix="/api/v1/source-viewer", tags=["SourceViewer"])


def get_original_use_case() -> GetOriginalUseCase:
    raise NotImplementedError


def _raise_http(e: Exception) -> None:
    """KB 라우터 _raise_http 규약 + 원본 전용 2종."""
    if isinstance(e, PermissionError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    if isinstance(e, OriginalNotAvailableError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.code)
    if isinstance(e, UnsupportedOriginalError):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=e.code,
        )
    if "not found" in str(e):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e),
    )


@router.get(
    "/kb/{kb_id}/documents/{document_id}/original",
    response_class=Response,
    description=(
        "근거 칩 원문 뷰어용 원본 파일(pdf/docx, inline). KB 읽기 권한 검사 후 반환한다. "
        "원본이 보관되지 않은 문서는 404 ORIGINAL_NOT_AVAILABLE — 텍스트 뷰어로 대체한다."
    ),
)
async def get_original(
    kb_id: str,
    document_id: str,
    current_user: User = Depends(get_current_user),
    use_case: GetOriginalUseCase = Depends(get_original_use_case),
) -> Response:
    request_id = str(uuid.uuid4())
    try:
        original = await use_case.execute(kb_id, document_id, current_user, request_id)
    except (PermissionError, LookupError, ValueError) as e:
        _raise_http(e)
    return Response(
        content=original.content,
        media_type=original.media_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(original.filename)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=300",
        },
    )
