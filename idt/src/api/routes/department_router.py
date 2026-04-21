"""Department Router: 부서 CRUD + 사용자-부서 관리 API."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import get_current_user, require_role

from src.application.department.schemas import (
    AssignUserDepartmentRequest,
    CreateDepartmentRequest,
    DepartmentListResponse,
    DepartmentResponse,
    UpdateDepartmentRequest,
)

router = APIRouter(prefix="/api/v1", tags=["Department"])


# ── DI 플레이스홀더 (main.py에서 override) ──────────────────────────

def get_list_departments_use_case():
    raise NotImplementedError


def get_create_department_use_case():
    raise NotImplementedError


def get_update_department_use_case():
    raise NotImplementedError


def get_delete_department_use_case():
    raise NotImplementedError


def get_assign_user_department_use_case():
    raise NotImplementedError


def get_remove_user_department_use_case():
    raise NotImplementedError


# ── 엔드포인트 ────────────────────────────────────────────────────


@router.get("/departments", response_model=DepartmentListResponse)
async def list_departments(
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_list_departments_use_case),
):
    request_id = str(uuid.uuid4())
    return await use_case.execute(request_id)


@router.post(
    "/departments",
    response_model=DepartmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_department(
    body: CreateDepartmentRequest,
    current_user: User = Depends(require_role("admin")),
    use_case=Depends(get_create_department_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(body, request_id)
    except ValueError as e:
        msg = str(e)
        if "이미 존재" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)


@router.patch("/departments/{dept_id}", response_model=DepartmentResponse)
async def update_department(
    dept_id: str,
    body: UpdateDepartmentRequest,
    current_user: User = Depends(require_role("admin")),
    use_case=Depends(get_update_department_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(dept_id, body, request_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete(
    "/departments/{dept_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_department(
    dept_id: str,
    current_user: User = Depends(require_role("admin")),
    use_case=Depends(get_delete_department_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        await use_case.execute(dept_id, request_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/users/{user_id}/departments",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def assign_user_department(
    user_id: int,
    body: AssignUserDepartmentRequest,
    current_user: User = Depends(require_role("admin")),
    use_case=Depends(get_assign_user_department_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        await use_case.execute(user_id, body, request_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.delete(
    "/users/{user_id}/departments/{dept_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_user_department(
    user_id: int,
    dept_id: str,
    current_user: User = Depends(require_role("admin")),
    use_case=Depends(get_remove_user_department_use_case),
):
    request_id = str(uuid.uuid4())
    await use_case.execute(user_id, dept_id, request_id)
