"""Admin user permission router: 사용자별 권한 부여/회수 + 사용자 생성/목록.

agent-user-context Design §6.4:
- admin 권한이 있는 사용자만 호출 가능 (require_role('admin'))
- POST /api/v1/admin/users/{user_id}/permissions — 권한 부여
- DELETE /api/v1/admin/users/{user_id}/permissions/{code} — 권한 회수
- GET    /api/v1/admin/users/{user_id}/permissions — 현재 권한 조회

admin-user-registration Design §6.2:
- POST /api/v1/admin/users — 관리자 직접 사용자 생성 (즉시 approved)
- GET  /api/v1/admin/users — 전체 사용자 목록 (프로필 + 부서명)
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.application.auth.admin_create_user_use_case import (
    AdminCreateUserCommand,
    AdminCreateUserUseCase,
)
from src.application.auth.list_users_use_case import ListUsersUseCase
from src.application.permission.grant_revoke import (
    GrantPermissionUseCase,
    RevokePermissionUseCase,
)
from src.domain.auth.entities import User, UserStatus
from src.domain.auth.interfaces import UserListFilters
from src.domain.permission.interfaces import PermissionRepositoryInterface
from src.interfaces.dependencies.auth import require_role
from src.interfaces.schemas.auth.request import AdminCreateUserRequest
from src.interfaces.schemas.auth.response import (
    AdminCreateUserResponse,
    AdminUserListItemResponse,
    AdminUserListResponse,
)


router = APIRouter(prefix="/api/v1/admin/users", tags=["Admin"])


# ── DI placeholder — main.py에서 override ─────────────────────────


def get_grant_permission_use_case() -> GrantPermissionUseCase:
    raise NotImplementedError


def get_revoke_permission_use_case() -> RevokePermissionUseCase:
    raise NotImplementedError


def get_permission_repository() -> PermissionRepositoryInterface:
    raise NotImplementedError


def get_admin_create_user_use_case() -> AdminCreateUserUseCase:
    raise NotImplementedError


def get_list_users_use_case() -> ListUsersUseCase:
    raise NotImplementedError


# ── Schemas ────────────────────────────────────────────────────────


class GrantPermissionRequest(BaseModel):
    code: str = Field(
        ..., min_length=1, max_length=64,
        pattern=r"^[A-Z][A-Z0-9_]*$",
        description="권한 코드 (UPPER_SNAKE)",
    )


class UserPermissionsResponse(BaseModel):
    user_id: int
    role_permissions: list[str]
    user_permissions: list[str]


# ── Endpoints: 사용자 생성/목록 (admin-user-registration) ──────────


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=AdminCreateUserResponse,
)
async def create_user(
    body: AdminCreateUserRequest,
    admin: User = Depends(require_role("admin")),
    use_case: AdminCreateUserUseCase = Depends(get_admin_create_user_use_case),
):
    """관리자가 직원 계정을 즉시 활성(approved) 상태로 생성."""
    request_id = str(uuid.uuid4())
    try:
        r = await use_case.execute(
            AdminCreateUserCommand(**body.model_dump()),
            request_id=request_id,
            created_by=admin.id,
        )
    except ValueError as e:
        msg = str(e)
        if "already registered" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg
        )

    return AdminCreateUserResponse(
        id=r.user_id,
        email=r.email,
        role=r.role,
        status=r.status,
        display_name=r.display_name,
        position=r.position,
        employee_no=r.employee_no,
        joined_at=r.joined_at.isoformat() if r.joined_at else None,
        department_id=r.department_id,
    )


@router.get("", response_model=AdminUserListResponse)
async def list_users(
    status_filter: str | None = Query(None, alias="status"),
    q: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _admin: User = Depends(require_role("admin")),
    use_case: ListUsersUseCase = Depends(get_list_users_use_case),
):
    """전체 사용자 목록 (프로필 + 부서명, 상태 필터/검색/페이지네이션)."""
    request_id = str(uuid.uuid4())
    try:
        parsed_status = UserStatus(status_filter) if status_filter else None
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status: {status_filter}",
        )

    result = await use_case.execute(
        UserListFilters(status=parsed_status, query=q, limit=limit, offset=offset),
        request_id=request_id,
    )
    return AdminUserListResponse(
        items=[
            AdminUserListItemResponse(
                id=i.id,
                email=i.email,
                role=i.role,
                status=i.status,
                display_name=i.display_name,
                position=i.position,
                department_names=i.department_names,
                created_at=i.created_at.isoformat() if i.created_at else None,
            )
            for i in result.items
        ],
        total=result.total,
    )


# ── Endpoints: 권한 부여/회수 ──────────────────────────────────────


@router.post("/{user_id}/permissions", status_code=status.HTTP_204_NO_CONTENT)
async def grant_permission(
    user_id: int,
    body: GrantPermissionRequest,
    admin: User = Depends(require_role("admin")),
    use_case: GrantPermissionUseCase = Depends(get_grant_permission_use_case),
):
    """user에게 권한 부여. idempotent — 이미 있으면 무시."""
    request_id = str(uuid.uuid4())
    try:
        await use_case.execute(
            user_id=user_id,
            code=body.code,
            granted_by=admin.id,
            request_id=request_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e),
        )


@router.delete(
    "/{user_id}/permissions/{code}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_permission(
    user_id: int,
    code: str,
    _admin: User = Depends(require_role("admin")),
    use_case: RevokePermissionUseCase = Depends(get_revoke_permission_use_case),
):
    """user에게 부여된 권한 회수. idempotent — 없어도 에러 X."""
    request_id = str(uuid.uuid4())
    try:
        await use_case.execute(
            user_id=user_id, code=code, request_id=request_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e),
        )


@router.get(
    "/{user_id}/permissions",
    response_model=UserPermissionsResponse,
)
async def list_user_permissions(
    user_id: int,
    admin: User = Depends(require_role("admin")),
    perm_repo: PermissionRepositoryInterface = Depends(get_permission_repository),
):
    """user의 role 기본 권한 + 추가 grant를 함께 반환."""
    request_id = str(uuid.uuid4())
    # 대상 user의 role을 알아야 role 기본 권한을 조회 가능.
    # 본 PR은 단순화를 위해 role을 받지 않고 user_permissions만 반환 후
    # role 권한은 require_role 받은 admin이 별도 API(예: role mgmt)로 조회.
    # 단순 구현: user 본인 권한만.
    user_codes = await perm_repo.find_codes_for_user(user_id, request_id)
    return UserPermissionsResponse(
        user_id=user_id,
        role_permissions=[],  # 호출자가 user의 role을 알면 별도 조회.
        user_permissions=user_codes,
    )
