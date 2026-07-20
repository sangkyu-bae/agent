"""Auth router: /api/v1/auth/*"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.auth.login_use_case import LoginRequest, LoginUseCase
from src.application.auth.logout_use_case import LogoutRequest, LogoutUseCase
from src.application.auth.refresh_token_use_case import RefreshTokenRequest, RefreshTokenUseCase
from src.application.auth.register_use_case import RegisterRequest, RegisterUseCase
from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import get_current_user
from src.interfaces.schemas.auth.request import (
    LoginRequest as LoginAPIRequest,
    LogoutRequest as LogoutAPIRequest,
    RefreshRequest,
    RegisterRequest as RegisterAPIRequest,
)
from src.interfaces.schemas.auth.response import (
    AccessTokenResponse,
    DepartmentBriefResponse,
    MeResponse,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def get_register_use_case() -> RegisterUseCase:
    raise NotImplementedError("RegisterUseCase not initialized")


def get_user_departments_use_case():
    raise NotImplementedError("GetUserDepartmentsUseCase not initialized")


def get_login_use_case() -> LoginUseCase:
    raise NotImplementedError("LoginUseCase not initialized")


def get_refresh_use_case() -> RefreshTokenUseCase:
    raise NotImplementedError("RefreshTokenUseCase not initialized")


def get_logout_use_case() -> LogoutUseCase:
    raise NotImplementedError("LogoutUseCase not initialized")


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
async def register(
    body: RegisterAPIRequest,
    use_case: RegisterUseCase = Depends(get_register_use_case),
) -> UserResponse:
    """회원가입. 가입 즉시 status=pending, 관리자 승인 후 로그인 가능."""
    request_id = str(uuid.uuid4())
    try:
        result = await use_case.execute(
            RegisterRequest(
                email=body.email,
                password=body.password,
                display_name=body.display_name,
            ),
            request_id=request_id,
        )
    except ValueError as e:
        msg = str(e)
        if "already registered" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)

    return UserResponse(
        id=result.user_id, email=result.email,
        role=result.role, status=result.status,
        display_name=result.display_name,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginAPIRequest,
    use_case: LoginUseCase = Depends(get_login_use_case),
) -> TokenResponse:
    """로그인. approved 상태 사용자만 허용."""
    request_id = str(uuid.uuid4())
    try:
        result = await use_case.execute(
            LoginRequest(email=body.email, password=body.password),
            request_id=request_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    return TokenResponse(access_token=result.access_token, refresh_token=result.refresh_token)


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(
    body: RefreshRequest,
    use_case: RefreshTokenUseCase = Depends(get_refresh_use_case),
) -> AccessTokenResponse:
    """Access Token 재발급."""
    request_id = str(uuid.uuid4())
    try:
        result = await use_case.execute(
            RefreshTokenRequest(refresh_token=body.refresh_token),
            request_id=request_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    return AccessTokenResponse(access_token=result.access_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: LogoutAPIRequest,
    current_user: User = Depends(get_current_user),
    use_case: LogoutUseCase = Depends(get_logout_use_case),
) -> None:
    """로그아웃. Refresh Token 무효화."""
    request_id = str(uuid.uuid4())
    await use_case.execute(
        LogoutRequest(refresh_token=body.refresh_token),
        request_id=request_id,
    )


@router.get("/me", response_model=MeResponse)
async def me(
    current_user: User = Depends(get_current_user),
    dept_uc=Depends(get_user_departments_use_case),
) -> MeResponse:
    """현재 로그인된 사용자 정보 조회 — 소속 부서 포함 (expose-user-department)."""
    request_id = str(uuid.uuid4())
    briefs = await dept_uc.execute(current_user.id, request_id)
    return MeResponse(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role.value,
        status=current_user.status.value,
        departments=[
            DepartmentBriefResponse(id=b.id, name=b.name, is_primary=b.is_primary)
            for b in briefs
        ],
    )
