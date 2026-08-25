"""Admin blueprint router: /api/v1/admin/blueprints/* + /api/v1/blueprints/options

Design Ref: golden-sample-blueprint §4.1/§4.2 (엔드포인트), §6.1 (오류 코드).
라우터는 변환·오류 매핑만 한다 — 검증은 도메인 VO(ValueError→400)·UseCase.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import PurePath

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi import status as http
from pydantic import ValidationError

from src.application.blueprint.admin_use_case import BlueprintAdminUseCase
from src.application.blueprint.extraction_use_case import BlueprintExtractionUseCase
from src.domain.auth.entities import User
from src.domain.blueprint.errors import (
    BlueprintNotFoundError,
    BlueprintValidationError,
    SampleExtractionError,
    UnsupportedSampleFormatError,
)
from src.domain.multimodal.errors import (
    MultimodalDisabledError,
    MultimodalNotConfiguredError,
    UnsupportedVisionProviderError,
)
from src.interfaces.dependencies.auth import get_current_user, require_role
from src.interfaces.schemas.blueprint import (
    BlueprintCreateRequest,
    BlueprintExtractResponse,
    BlueprintOption,
    BlueprintOptionsResponse,
    BlueprintResponse,
    BlueprintSummary,
    BlueprintUpdateRequest,
    FontsResponse,
)

router = APIRouter(prefix="/api/v1/admin/blueprints", tags=["admin-blueprints"])
options_router = APIRouter(prefix="/api/v1/blueprints", tags=["blueprints"])

MAX_UPLOAD_BYTES = 30 * 1024 * 1024
DEFAULT_MAX_PAGES = 60
MAX_PAGES_LIMIT = 200
_ALLOWED_EXT = {".pdf", ".pptx"}


def get_blueprint_extraction_use_case() -> BlueprintExtractionUseCase:
    raise NotImplementedError("Configure via dependency_overrides")


def get_blueprint_admin_use_case() -> BlueprintAdminUseCase:
    raise NotImplementedError("Configure via dependency_overrides")


def get_blueprint_thumbnailer() -> Callable[[bytes], str | None]:
    raise NotImplementedError("Configure via dependency_overrides")


def _error(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message}
    )


def _validation(body: dict, model):
    try:
        return model.model_validate(body)
    except ValidationError as e:
        raise _error("VALIDATION_ERROR", str(e.errors()[0].get("msg", e)), 400) from e


@router.post("/extract", response_model=BlueprintExtractResponse)
async def extract(
    file: UploadFile = File(...),
    max_pages: int = Query(DEFAULT_MAX_PAGES),
    current_user: User = Depends(require_role("admin")),
    use_case: BlueprintExtractionUseCase = Depends(get_blueprint_extraction_use_case),
    thumbnailer: Callable[[bytes], str | None] = Depends(get_blueprint_thumbnailer),
) -> BlueprintExtractResponse:
    if not 1 <= max_pages <= MAX_PAGES_LIMIT:
        raise _error(
            "VALIDATION_ERROR", f"max_pages must be within 1..{MAX_PAGES_LIMIT}", 400
        )
    filename = file.filename or ""
    if PurePath(filename).suffix.lower() not in _ALLOWED_EXT:
        raise _error("UNSUPPORTED_MEDIA", "pdf 또는 pptx 파일만 지원합니다", 415)
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise _error("PAYLOAD_TOO_LARGE", "30MB 를 초과했습니다", 413)
    try:
        outcome = await use_case.run(
            data, filename, max_pages, f"admin-bp-{current_user.id}"
        )
    except (UnsupportedSampleFormatError, SampleExtractionError) as e:
        raise _error("UNSUPPORTED_MEDIA", str(e), 415) from e
    except MultimodalDisabledError as e:
        raise _error("MULTIMODAL_DISABLED", str(e), 409) from e
    except MultimodalNotConfiguredError as e:
        raise _error("MULTIMODAL_NOT_CONFIGURED", str(e), 409) from e
    except UnsupportedVisionProviderError as e:
        raise _error("UNSUPPORTED_VISION_PROVIDER", str(e), 500) from e
    return BlueprintExtractResponse.from_outcome(outcome, thumbnailer)


@router.post("", response_model=BlueprintResponse, status_code=http.HTTP_201_CREATED)
async def create(
    body: dict,
    current_user: User = Depends(require_role("admin")),
    use_case: BlueprintAdminUseCase = Depends(get_blueprint_admin_use_case),
) -> BlueprintResponse:
    req = _validation(body, BlueprintCreateRequest)
    try:
        blueprint = req.draft.to_domain()
        asset_bytes = {a.id: a.decode() for a in req.assets}
        saved = await use_case.create(blueprint, asset_bytes, str(current_user.id))
    except (ValueError, BlueprintValidationError) as e:
        raise _error("VALIDATION_ERROR", str(e), 400) from e
    return BlueprintResponse.from_domain(saved)


@router.get("", response_model=list[BlueprintSummary])
async def list_blueprints(
    include_inactive: bool = Query(True),
    current_user: User = Depends(require_role("admin")),
    use_case: BlueprintAdminUseCase = Depends(get_blueprint_admin_use_case),
) -> list[BlueprintSummary]:
    items = await use_case.list(include_inactive=include_inactive)
    return [BlueprintSummary.from_domain(b) for b in items]


@router.get("/fonts", response_model=FontsResponse)
async def fonts(
    current_user: User = Depends(require_role("admin")),
    use_case: BlueprintAdminUseCase = Depends(get_blueprint_admin_use_case),
) -> FontsResponse:
    view = use_case.fonts()
    return FontsResponse(installed=list(view.installed), default=view.default)


@router.get("/{blueprint_id}", response_model=BlueprintResponse)
async def get_blueprint(
    blueprint_id: str,
    current_user: User = Depends(require_role("admin")),
    use_case: BlueprintAdminUseCase = Depends(get_blueprint_admin_use_case),
) -> BlueprintResponse:
    try:
        return BlueprintResponse.from_domain(await use_case.get(blueprint_id))
    except BlueprintNotFoundError as e:
        raise _error("BLUEPRINT_NOT_FOUND", str(e), 404) from e


@router.put("/{blueprint_id}", response_model=BlueprintResponse)
async def update_blueprint(
    blueprint_id: str,
    body: dict,
    current_user: User = Depends(require_role("admin")),
    use_case: BlueprintAdminUseCase = Depends(get_blueprint_admin_use_case),
) -> BlueprintResponse:
    req = _validation(body, BlueprintUpdateRequest)
    try:
        updated = await use_case.update(blueprint_id, req.draft.to_domain())
    except BlueprintNotFoundError as e:
        raise _error("BLUEPRINT_NOT_FOUND", str(e), 404) from e
    except (ValueError, BlueprintValidationError) as e:
        raise _error("VALIDATION_ERROR", str(e), 400) from e
    return BlueprintResponse.from_domain(updated)


@router.delete("/{blueprint_id}", response_model=BlueprintResponse)
async def deactivate_blueprint(
    blueprint_id: str,
    current_user: User = Depends(require_role("admin")),
    use_case: BlueprintAdminUseCase = Depends(get_blueprint_admin_use_case),
) -> BlueprintResponse:
    try:
        return BlueprintResponse.from_domain(await use_case.deactivate(blueprint_id))
    except BlueprintNotFoundError as e:
        raise _error("BLUEPRINT_NOT_FOUND", str(e), 404) from e


@router.get("/{blueprint_id}/assets/{asset_id}")
async def get_asset(
    blueprint_id: str,
    asset_id: str,
    current_user: User = Depends(require_role("admin")),
    use_case: BlueprintAdminUseCase = Depends(get_blueprint_admin_use_case),
) -> Response:
    try:
        stored = await use_case.asset(blueprint_id, asset_id)
    except BlueprintNotFoundError as e:
        raise _error("BLUEPRINT_NOT_FOUND", str(e), 404) from e
    return Response(content=stored.data, media_type=stored.asset.mime)


@options_router.get("/options", response_model=BlueprintOptionsResponse)
async def blueprint_options(
    current_user: User = Depends(get_current_user),
    use_case: BlueprintAdminUseCase = Depends(get_blueprint_admin_use_case),
) -> BlueprintOptionsResponse:
    items = await use_case.options()
    return BlueprintOptionsResponse(
        items=[BlueprintOption(id=i, name=n) for i, n in items]
    )
