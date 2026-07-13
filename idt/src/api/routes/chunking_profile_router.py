"""Chunking Profile Router: 사용자 조회 API (clause-aware-chunking Design §8.2, D14).

KB 생성 폼 / 에이전트 빌더 프리필용. active 프로파일 목록(is_default 포함)을 반환한다.
관리자 CRUD와 동일한 UseCase/응답 모델을 재사용한다.
"""
import uuid

from fastapi import APIRouter, Depends

from src.api.routes.admin_chunking_router import (
    ProfileListResponse,
    _to_response,
    get_chunking_profile_use_case,
)
from src.application.chunking_profile.use_case import ChunkingProfileUseCase
from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import get_current_user

router = APIRouter(prefix="/api/v1/chunking", tags=["Chunking"])


@router.get("/profiles", response_model=ProfileListResponse)
async def list_chunking_profiles(
    current_user: User = Depends(get_current_user),
    use_case: ChunkingProfileUseCase = Depends(get_chunking_profile_use_case),
):
    request_id = str(uuid.uuid4())
    profiles = await use_case.list_active(request_id)
    return ProfileListResponse(
        profiles=[_to_response(p) for p in profiles],
        total=len(profiles),
    )
