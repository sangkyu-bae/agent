"""Admin multimodal router: /api/v1/admin/multimodal/*

Design Ref: multimodal-extractor §4.1/§4.2 (settings GET/PUT, test POST),
§6.1 (오류 코드).
라우터는 변환·오류 매핑만 한다 — 검증·모델 해석은 UseCase/도메인 VO.
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import ValidationError

from src.application.multimodal.settings_use_case import (
    MultimodalSettingsUseCase,
    VisionModelNotCapableError,
    VisionModelNotFoundError,
)
from src.domain.auth.entities import User
from src.domain.multimodal.errors import (
    MultimodalNotConfiguredError,
    UnsupportedVisionProviderError,
)
from src.interfaces.dependencies.auth import require_role
from src.interfaces.schemas.multimodal import (
    ConnectionTestResponse,
    MultimodalSettingsRequest,
    MultimodalSettingsResponse,
)

router = APIRouter(prefix="/api/v1/admin/multimodal", tags=["admin-multimodal"])

_TEST_IMAGE_MAX_BYTES = 5 * 1024 * 1024
_IMAGE_MIMES = {"image/png", "image/jpeg", "image/webp"}


def get_multimodal_settings_use_case() -> MultimodalSettingsUseCase:
    raise NotImplementedError("MultimodalSettingsUseCase not initialized")


def _error(code: str, message: str, http_status: int) -> HTTPException:
    return HTTPException(
        status_code=http_status, detail={"code": code, "message": message}
    )


@router.get("/settings", response_model=MultimodalSettingsResponse)
async def get_settings(
    current_user: User = Depends(require_role("admin")),
    use_case: MultimodalSettingsUseCase = Depends(get_multimodal_settings_use_case),
) -> MultimodalSettingsResponse:
    view = await use_case.get(request_id=f"admin-mm-{current_user.id}")
    return MultimodalSettingsResponse.from_view(view)


@router.put("/settings", response_model=MultimodalSettingsResponse)
async def put_settings(
    body: dict,
    current_user: User = Depends(require_role("admin")),
    use_case: MultimodalSettingsUseCase = Depends(get_multimodal_settings_use_case),
) -> MultimodalSettingsResponse:
    # 스키마 검증 실패를 422 대신 400 VALIDATION_ERROR 로 통일 (Design §6.1)
    try:
        req = MultimodalSettingsRequest.model_validate(body)
    except ValidationError as e:
        raise _error("VALIDATION_ERROR", str(e.errors()[0].get("msg", e)), 400) from e
    try:
        view = await use_case.update(req.to_update(), f"admin-mm-{current_user.id}")
    except VisionModelNotFoundError as e:
        raise _error("VISION_MODEL_NOT_FOUND", str(e), status.HTTP_404_NOT_FOUND) from e
    except VisionModelNotCapableError as e:
        raise _error(
            "VISION_MODEL_NOT_CAPABLE", str(e), status.HTTP_409_CONFLICT
        ) from e
    except ValueError as e:
        raise _error("VALIDATION_ERROR", str(e), status.HTTP_400_BAD_REQUEST) from e
    return MultimodalSettingsResponse.from_view(view)


@router.post("/test", response_model=ConnectionTestResponse)
async def test_connection(
    image: UploadFile | None = File(None, description="선택 — 없으면 내장 샘플 차트"),
    current_user: User = Depends(require_role("admin")),
    use_case: MultimodalSettingsUseCase = Depends(get_multimodal_settings_use_case),
) -> ConnectionTestResponse:
    data, mime = await _read_test_image(image)
    try:
        result = await use_case.test_connection(
            data, mime, f"admin-mm-{current_user.id}"
        )
    except MultimodalNotConfiguredError as e:
        raise _error(
            "MULTIMODAL_NOT_CONFIGURED", str(e), status.HTTP_409_CONFLICT
        ) from e
    except UnsupportedVisionProviderError as e:
        # Design §6.1: 설정된 provider 에 등록된 어댑터가 없음 — 관리자 조치 필요
        raise _error(
            "UNSUPPORTED_VISION_PROVIDER",
            str(e),
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from e
    return ConnectionTestResponse.from_result(result)


async def _read_test_image(image: UploadFile | None) -> tuple[bytes | None, str]:
    if image is None or not image.filename:
        return None, "image/png"
    mime = image.content_type or ""
    if mime not in _IMAGE_MIMES:
        raise _error(
            "UNSUPPORTED_MEDIA",
            f"image must be one of {sorted(_IMAGE_MIMES)}",
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )
    data = await image.read()
    if len(data) > _TEST_IMAGE_MAX_BYTES:
        raise _error(
            "PAYLOAD_TOO_LARGE", "image exceeds 5MB", status.HTTP_413_CONTENT_TOO_LARGE
        )
    return data, mime
