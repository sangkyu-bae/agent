"""Admin Tool Access Router — 기본 세트 / 부서 / 사용자 도구 허용 조회·전체 교체.

Design Ref: tool-access-control §4.1, §4.2 (Plan FR-04) — 전부 admin 전용.
오류 매핑: UnknownToolIdsError → 400 UNKNOWN_TOOL_IDS(tool_ids 포함), LookupError → 404.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.tool_access.schemas import (
    DefaultToolAccessResponse,
    DepartmentToolAccessResponse,
    ReplaceToolAccessRequest,
    UserToolAccessResponse,
)
from src.domain.auth.entities import User
from src.domain.tool_access.exceptions import UnknownToolIdsError
from src.interfaces.dependencies.auth import require_role

router = APIRouter(prefix="/api/v1/admin/tool-access", tags=["Admin Tool Access"])


# ── DI 플레이스홀더 (main.py에서 override) ──────────────────────────

def get_default_tool_access_use_case():
    raise NotImplementedError


def get_department_tool_access_use_case():
    raise NotImplementedError


def get_user_tool_access_use_case():
    raise NotImplementedError


def _unknown_tool_ids(e: UnknownToolIdsError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "code": "UNKNOWN_TOOL_IDS",
            "message": "카탈로그에 없는 도구가 포함되어 있습니다",
            "tool_ids": list(e.tool_ids),
        },
    )


def _not_found(e: LookupError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ── 기본 세트 ──────────────────────────────────────────────────────

@router.get("/default", response_model=DefaultToolAccessResponse)
async def get_default_tool_access(
    current_user: User = Depends(require_role("admin")),
    use_case=Depends(get_default_tool_access_use_case),
):
    return await use_case.get(str(uuid.uuid4()))


@router.put("/default", response_model=DefaultToolAccessResponse)
async def replace_default_tool_access(
    body: ReplaceToolAccessRequest,
    current_user: User = Depends(require_role("admin")),
    use_case=Depends(get_default_tool_access_use_case),
):
    try:
        return await use_case.replace(
            body.tool_ids, granted_by=current_user.id, request_id=str(uuid.uuid4())
        )
    except UnknownToolIdsError as e:
        raise _unknown_tool_ids(e)


# ── 부서 ───────────────────────────────────────────────────────────

@router.get(
    "/departments/{department_id}", response_model=DepartmentToolAccessResponse
)
async def get_department_tool_access(
    department_id: str,
    current_user: User = Depends(require_role("admin")),
    use_case=Depends(get_department_tool_access_use_case),
):
    try:
        return await use_case.get(department_id, str(uuid.uuid4()))
    except LookupError as e:
        raise _not_found(e)


@router.put(
    "/departments/{department_id}", response_model=DepartmentToolAccessResponse
)
async def replace_department_tool_access(
    department_id: str,
    body: ReplaceToolAccessRequest,
    current_user: User = Depends(require_role("admin")),
    use_case=Depends(get_department_tool_access_use_case),
):
    try:
        return await use_case.replace(
            department_id, body.tool_ids,
            granted_by=current_user.id, request_id=str(uuid.uuid4()),
        )
    except UnknownToolIdsError as e:
        raise _unknown_tool_ids(e)
    except LookupError as e:
        raise _not_found(e)


# ── 사용자 ─────────────────────────────────────────────────────────

@router.get("/users/{user_id}", response_model=UserToolAccessResponse)
async def get_user_tool_access(
    user_id: int,
    current_user: User = Depends(require_role("admin")),
    use_case=Depends(get_user_tool_access_use_case),
):
    try:
        return await use_case.get(user_id, str(uuid.uuid4()))
    except LookupError as e:
        raise _not_found(e)


@router.put("/users/{user_id}", response_model=UserToolAccessResponse)
async def replace_user_tool_access(
    user_id: int,
    body: ReplaceToolAccessRequest,
    current_user: User = Depends(require_role("admin")),
    use_case=Depends(get_user_tool_access_use_case),
):
    try:
        return await use_case.replace(
            user_id, body.tool_ids,
            granted_by=current_user.id, request_id=str(uuid.uuid4()),
        )
    except UnknownToolIdsError as e:
        raise _unknown_tool_ids(e)
    except LookupError as e:
        raise _not_found(e)
