"""Admin Chunking Router: 관리자 전용 청킹 프로파일 CRUD (clause-aware-chunking Design §8.1).

모든 엔드포인트 require_role('admin') 가드. DI 플레이스홀더 + main.py override 패턴.
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.application.chunking_profile.use_case import ChunkingProfileUseCase
from src.domain.auth.entities import User
from src.domain.chunking_profile.entities import BoundaryRule, ChunkingProfile
from src.interfaces.dependencies.auth import require_role

router = APIRouter(prefix="/api/v1/admin/chunking", tags=["Admin"])


# ── DI 플레이스홀더 (main.py에서 override) ──────────────────────────

def get_chunking_profile_use_case() -> ChunkingProfileUseCase:
    raise NotImplementedError


# ── Schemas ──────────────────────────────────────────────────────

class BoundaryRuleBody(BaseModel):
    pattern: str
    priority: int = 1
    level: str  # "parent" | "child"


class ChunkingProfileBody(BaseModel):
    name: str
    description: str | None = None
    boundary_rules: list[BoundaryRuleBody]
    parent_chunk_size: int = 2000
    chunk_size: int = 500
    chunk_overlap: int = 50
    is_default: bool = False
    # card-section-summary D2: 섹션 요약 LLM 지정 (None=요약 비활성)
    summary_llm_model_id: str | None = None


class ProfileResponse(BaseModel):
    profile_id: str
    name: str
    description: str | None
    boundary_rules: list[dict]
    parent_chunk_size: int
    chunk_size: int
    chunk_overlap: int
    is_default: bool
    summary_llm_model_id: str | None = None
    created_at: datetime | None
    updated_at: datetime | None


class ProfileListResponse(BaseModel):
    profiles: list[ProfileResponse]
    total: int


class ProfileMessageResponse(BaseModel):
    profile_id: str
    message: str


def _to_response(profile: ChunkingProfile) -> ProfileResponse:
    return ProfileResponse(
        profile_id=profile.id,
        name=profile.name,
        description=profile.description,
        boundary_rules=[
            {"pattern": r.pattern, "priority": r.priority, "level": r.level}
            for r in profile.boundary_rules
        ],
        parent_chunk_size=profile.parent_chunk_size,
        chunk_size=profile.chunk_size,
        chunk_overlap=profile.chunk_overlap,
        is_default=profile.is_default,
        summary_llm_model_id=profile.summary_llm_model_id,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def _to_rules(body: ChunkingProfileBody) -> list[BoundaryRule]:
    return [
        BoundaryRule(pattern=r.pattern, priority=r.priority, level=r.level)
        for r in body.boundary_rules
    ]


def _raise_http(e: Exception) -> None:
    msg = str(e)
    if "not found" in msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    if "already exists" in msg:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg
    )


# ── Endpoints ─────────────────────────────────────────────────────

@router.post("/profiles", status_code=201, response_model=ProfileResponse)
async def create_profile(
    body: ChunkingProfileBody,
    current_user: User = Depends(require_role("admin")),
    use_case: ChunkingProfileUseCase = Depends(get_chunking_profile_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        profile = await use_case.create(
            name=body.name,
            boundary_rules=_to_rules(body),
            parent_chunk_size=body.parent_chunk_size,
            chunk_size=body.chunk_size,
            chunk_overlap=body.chunk_overlap,
            description=body.description,
            is_default=body.is_default,
            request_id=request_id,
            summary_llm_model_id=body.summary_llm_model_id,
        )
    except ValueError as e:
        _raise_http(e)
    return _to_response(profile)


@router.get("/profiles", response_model=ProfileListResponse)
async def list_profiles(
    current_user: User = Depends(require_role("admin")),
    use_case: ChunkingProfileUseCase = Depends(get_chunking_profile_use_case),
):
    request_id = str(uuid.uuid4())
    profiles = await use_case.list_active(request_id)
    return ProfileListResponse(
        profiles=[_to_response(p) for p in profiles],
        total=len(profiles),
    )


@router.get("/profiles/{profile_id}", response_model=ProfileResponse)
async def get_profile(
    profile_id: str,
    current_user: User = Depends(require_role("admin")),
    use_case: ChunkingProfileUseCase = Depends(get_chunking_profile_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        profile = await use_case.get(profile_id, request_id)
    except ValueError as e:
        _raise_http(e)
    return _to_response(profile)


@router.put("/profiles/{profile_id}", response_model=ProfileResponse)
async def update_profile(
    profile_id: str,
    body: ChunkingProfileBody,
    current_user: User = Depends(require_role("admin")),
    use_case: ChunkingProfileUseCase = Depends(get_chunking_profile_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        profile = await use_case.update(
            profile_id=profile_id,
            name=body.name,
            boundary_rules=_to_rules(body),
            parent_chunk_size=body.parent_chunk_size,
            chunk_size=body.chunk_size,
            chunk_overlap=body.chunk_overlap,
            description=body.description,
            is_default=body.is_default,
            request_id=request_id,
            summary_llm_model_id=body.summary_llm_model_id,
        )
    except ValueError as e:
        _raise_http(e)
    return _to_response(profile)


@router.put("/profiles/{profile_id}/default", response_model=ProfileMessageResponse)
async def set_default_profile(
    profile_id: str,
    current_user: User = Depends(require_role("admin")),
    use_case: ChunkingProfileUseCase = Depends(get_chunking_profile_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        await use_case.set_default(profile_id, request_id)
    except ValueError as e:
        _raise_http(e)
    return ProfileMessageResponse(
        profile_id=profile_id, message="Default profile updated"
    )


@router.delete("/profiles/{profile_id}", response_model=ProfileMessageResponse)
async def delete_profile(
    profile_id: str,
    current_user: User = Depends(require_role("admin")),
    use_case: ChunkingProfileUseCase = Depends(get_chunking_profile_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        await use_case.delete(profile_id, request_id)
    except ValueError as e:
        _raise_http(e)
    return ProfileMessageResponse(
        profile_id=profile_id, message="Chunking profile deleted"
    )
