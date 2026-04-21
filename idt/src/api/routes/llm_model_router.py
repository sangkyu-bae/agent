"""LLM Model router: /api/v1/llm-models/*

LLM-MODEL-REG-001 §7.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.application.llm_model.create_llm_model_use_case import (
    CreateLlmModelUseCase,
)
from src.application.llm_model.deactivate_llm_model_use_case import (
    DeactivateLlmModelUseCase,
)
from src.application.llm_model.get_llm_model_use_case import GetLlmModelUseCase
from src.application.llm_model.list_llm_models_use_case import (
    ListLlmModelsUseCase,
)
from src.application.llm_model.schemas import (
    CreateLlmModelRequest,
    LlmModelListResponse,
    LlmModelResponse,
    UpdateLlmModelRequest,
)
from src.application.llm_model.update_llm_model_use_case import (
    UpdateLlmModelUseCase,
)
from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import get_current_user, require_role

router = APIRouter(prefix="/api/v1/llm-models", tags=["llm-models"])


# -------- DI placeholders (override in create_app()) --------


def get_create_llm_model_use_case() -> CreateLlmModelUseCase:
    raise NotImplementedError("CreateLlmModelUseCase not initialized")


def get_update_llm_model_use_case() -> UpdateLlmModelUseCase:
    raise NotImplementedError("UpdateLlmModelUseCase not initialized")


def get_deactivate_llm_model_use_case() -> DeactivateLlmModelUseCase:
    raise NotImplementedError("DeactivateLlmModelUseCase not initialized")


def get_get_llm_model_use_case() -> GetLlmModelUseCase:
    raise NotImplementedError("GetLlmModelUseCase not initialized")


def get_list_llm_models_use_case() -> ListLlmModelsUseCase:
    raise NotImplementedError("ListLlmModelsUseCase not initialized")


# -------- Endpoints --------


@router.get("", response_model=LlmModelListResponse)
async def list_llm_models(
    include_inactive: bool = Query(False, description="비활성 모델 포함 여부"),
    _: User = Depends(get_current_user),
    use_case: ListLlmModelsUseCase = Depends(get_list_llm_models_use_case),
) -> LlmModelListResponse:
    """활성 모델 목록 조회 (include_inactive=true 시 전체)."""
    request_id = str(uuid.uuid4())
    return await use_case.execute(include_inactive=include_inactive, request_id=request_id)


@router.get("/{model_id}", response_model=LlmModelResponse)
async def get_llm_model(
    model_id: str,
    _: User = Depends(get_current_user),
    use_case: GetLlmModelUseCase = Depends(get_get_llm_model_use_case),
) -> LlmModelResponse:
    """단일 모델 조회."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(model_id, request_id=request_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=LlmModelResponse,
)
async def create_llm_model(
    body: CreateLlmModelRequest,
    _: User = Depends(require_role("admin")),
    use_case: CreateLlmModelUseCase = Depends(get_create_llm_model_use_case),
) -> LlmModelResponse:
    """신규 모델 등록 (관리자 전용)."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(body, request_id=request_id)
    except ValueError as e:
        msg = str(e)
        if "이미 등록된" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)


@router.patch("/{model_id}", response_model=LlmModelResponse)
async def update_llm_model(
    model_id: str,
    body: UpdateLlmModelRequest,
    _: User = Depends(require_role("admin")),
    use_case: UpdateLlmModelUseCase = Depends(get_update_llm_model_use_case),
) -> LlmModelResponse:
    """모델 정보 수정 (관리자 전용)."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(model_id, body, request_id=request_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/{model_id}", response_model=LlmModelResponse)
async def deactivate_llm_model(
    model_id: str,
    _: User = Depends(require_role("admin")),
    use_case: DeactivateLlmModelUseCase = Depends(
        get_deactivate_llm_model_use_case
    ),
) -> LlmModelResponse:
    """모델 비활성화 (소프트 삭제, 관리자 전용)."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(model_id, request_id=request_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
