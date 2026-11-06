"""Admin kb-defaults router: /api/v1/admin/kb-defaults.

agent-kb-quick-setup Design §4.2. 라우터는 변환·오류 매핑만 한다 — 검증·모델
해석은 UseCase. 오류 형식은 admin_multimodal_router 와 동일.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError

from src.application.kb_default_setting.use_case import KbDefaultSettingUseCase
from src.domain.auth.entities import User
from src.domain.kb_default_setting.errors import (
    EmbeddingModelInactiveError,
    EmbeddingModelNotFoundError,
)
from src.interfaces.dependencies.auth import require_role
from src.interfaces.schemas.kb_defaults import (
    KbDefaultsResponse,
    KbDefaultsUpdateRequest,
)

router = APIRouter(prefix="/api/v1/admin/kb-defaults", tags=["admin-kb-defaults"])


def get_kb_default_setting_use_case() -> KbDefaultSettingUseCase:
    raise NotImplementedError("KbDefaultSettingUseCase not initialized")


def _error(code: str, message: str, http_status: int) -> HTTPException:
    return HTTPException(
        status_code=http_status, detail={"code": code, "message": message}
    )


@router.get("", response_model=KbDefaultsResponse)
async def get_kb_defaults(
    current_user: User = Depends(require_role("admin")),
    use_case: KbDefaultSettingUseCase = Depends(get_kb_default_setting_use_case),
) -> KbDefaultsResponse:
    view = await use_case.get(request_id=str(uuid.uuid4()))
    return KbDefaultsResponse.from_view(view)


@router.put("", response_model=KbDefaultsResponse)
async def put_kb_defaults(
    body: dict,
    current_user: User = Depends(require_role("admin")),
    use_case: KbDefaultSettingUseCase = Depends(get_kb_default_setting_use_case),
) -> KbDefaultsResponse:
    try:
        req = KbDefaultsUpdateRequest.model_validate(body)
    except ValidationError as e:
        msg = str(e.errors()[0].get("msg", e))
        raise _error("VALIDATION_ERROR", msg, status.HTTP_400_BAD_REQUEST) from e
    try:
        view = await use_case.update(req.default_embedding_model_id, str(uuid.uuid4()))
    except EmbeddingModelNotFoundError as e:
        raise _error(e.code, str(e), status.HTTP_404_NOT_FOUND) from e
    except EmbeddingModelInactiveError as e:
        raise _error(e.code, str(e), status.HTTP_409_CONFLICT) from e
    return KbDefaultsResponse.from_view(view)
