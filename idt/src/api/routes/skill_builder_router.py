"""Skill Builder Router: 재사용 Skill 생성/조회/수정/삭제/Fork API.

Plan/Design skill-builder: /api/v1/skills CRUD + Fork.
script_content는 저장 전용이며 실행되지 않는다(런타임은 후속 phase).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.application.skill_builder.schemas import (
    CreateSkillRequest,
    CreateSkillResponse,
    ForkSkillRequest,
    ForkSkillResponse,
    GetSkillResponse,
    ListSkillsRequest,
    ListSkillsResponse,
    UpdateSkillRequest,
    UpdateSkillResponse,
)
from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import get_current_user

router = APIRouter(prefix="/api/v1/skills", tags=["Skill Builder"])


# ── DI 플레이스홀더 (main.py에서 override) ──────────────────────────

def get_create_skill_use_case():
    raise NotImplementedError


def get_get_skill_use_case():
    raise NotImplementedError


def get_list_skills_use_case():
    raise NotImplementedError


def get_update_skill_use_case():
    raise NotImplementedError


def get_delete_skill_use_case():
    raise NotImplementedError


def get_fork_skill_use_case():
    raise NotImplementedError


def _viewer_dept_ids(user: User) -> list[str]:
    return list(getattr(user, "department_ids", []) or [])


# ── 엔드포인트 (/my·/list는 /{skill_id} 앞에 선언) ──────────────────


@router.post("", response_model=CreateSkillResponse, status_code=201)
async def create_skill(
    body: CreateSkillRequest,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_create_skill_use_case),
):
    """Skill 생성."""
    request_id = str(uuid.uuid4())
    body.user_id = str(current_user.id)
    try:
        return await use_case.execute(body, request_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/my", response_model=ListSkillsResponse)
async def list_my_skills(
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_list_skills_use_case),
):
    """내 Skill 목록."""
    request_id = str(uuid.uuid4())
    return await use_case.execute_my(
        str(current_user.id), current_user.role.value, request_id
    )


@router.post("/list", response_model=ListSkillsResponse)
async def list_skills(
    body: ListSkillsRequest,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_list_skills_use_case),
):
    """접근 가능한 Skill 목록 (가시성/RBAC 기반)."""
    request_id = str(uuid.uuid4())
    return await use_case.execute_accessible(
        viewer_user_id=str(current_user.id),
        viewer_role=current_user.role.value,
        request=body,
        request_id=request_id,
    )


@router.get("/{skill_id}", response_model=GetSkillResponse)
async def get_skill(
    skill_id: str,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_get_skill_use_case),
):
    """Skill 단건 조회."""
    request_id = str(uuid.uuid4())
    try:
        result = await use_case.execute(
            skill_id, request_id,
            viewer_user_id=str(current_user.id),
            viewer_role=current_user.role.value,
            viewer_department_ids=_viewer_dept_ids(current_user),
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="접근 권한 없음")
    if result is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return result


@router.put("/{skill_id}", response_model=UpdateSkillResponse)
async def update_skill(
    skill_id: str,
    body: UpdateSkillRequest,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_update_skill_use_case),
):
    """Skill 수정 (소유자)."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(
            skill_id, body, request_id, viewer_user_id=str(current_user.id)
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="수정 권한 없음")
    except ValueError as e:
        msg = str(e)
        raise HTTPException(
            status_code=404 if "찾을 수 없" in msg else 422, detail=msg
        )


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(
    skill_id: str,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_delete_skill_use_case),
):
    """Skill 소프트 삭제 (소유자 또는 admin)."""
    request_id = str(uuid.uuid4())
    try:
        await use_case.execute(
            skill_id=skill_id,
            viewer_user_id=str(current_user.id),
            viewer_role=current_user.role.value,
            request_id=request_id,
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="삭제 권한 없음")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{skill_id}/fork", response_model=ForkSkillResponse, status_code=201
)
async def fork_skill(
    skill_id: str,
    body: ForkSkillRequest | None = None,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_fork_skill_use_case),
):
    """Skill 포크 (전체 복제)."""
    request_id = str(uuid.uuid4())
    custom_name = body.name if body else None
    try:
        return await use_case.execute(
            source_skill_id=skill_id,
            user_id=str(current_user.id),
            custom_name=custom_name,
            request_id=request_id,
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="접근 권한 없음")
    except ValueError as e:
        msg = str(e)
        if "자신의" in msg or "삭제" in msg:
            raise HTTPException(status_code=400, detail=msg)
        raise HTTPException(status_code=404, detail=msg)
