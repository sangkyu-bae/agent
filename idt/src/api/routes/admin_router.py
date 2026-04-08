"""Admin router: /api/v1/admin/users/* (admin 전용)"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.auth.approve_user_use_case import ApproveUserRequest, ApproveUserUseCase
from src.application.auth.get_pending_users_use_case import GetPendingUsersUseCase
from src.application.auth.reject_user_use_case import RejectUserRequest, RejectUserUseCase
from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import require_role
from src.interfaces.schemas.auth.response import PendingUserResponse

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def get_pending_users_use_case() -> GetPendingUsersUseCase:
    raise NotImplementedError("GetPendingUsersUseCase not initialized")


def get_approve_use_case() -> ApproveUserUseCase:
    raise NotImplementedError("ApproveUserUseCase not initialized")


def get_reject_use_case() -> RejectUserUseCase:
    raise NotImplementedError("RejectUserUseCase not initialized")


@router.get("/users/pending", response_model=list[PendingUserResponse])
async def list_pending_users(
    admin: User = Depends(require_role("admin")),
    use_case: GetPendingUsersUseCase = Depends(get_pending_users_use_case),
) -> list[PendingUserResponse]:
    """승인 대기 중인 사용자 목록 조회 (admin 전용)."""
    request_id = str(uuid.uuid4())
    results = await use_case.execute(request_id=request_id)
    return [
        PendingUserResponse(
            id=r.id,
            email=r.email,
            role=r.role,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in results
    ]


@router.post("/users/{user_id}/approve", status_code=status.HTTP_204_NO_CONTENT)
async def approve_user(
    user_id: int,
    admin: User = Depends(require_role("admin")),
    use_case: ApproveUserUseCase = Depends(get_approve_use_case),
) -> None:
    """회원 승인 (admin 전용)."""
    request_id = str(uuid.uuid4())
    try:
        await use_case.execute(ApproveUserRequest(user_id=user_id), request_id=request_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/users/{user_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
async def reject_user(
    user_id: int,
    admin: User = Depends(require_role("admin")),
    use_case: RejectUserUseCase = Depends(get_reject_use_case),
) -> None:
    """회원 거절 (admin 전용)."""
    request_id = str(uuid.uuid4())
    try:
        await use_case.execute(RejectUserRequest(user_id=user_id), request_id=request_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
