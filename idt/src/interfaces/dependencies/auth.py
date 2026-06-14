"""FastAPI auth dependencies (get_current_user, require_role,
get_current_user_from_query_token, get_auth_context).

agent-run-streaming-sse Design §5.4: SSE/WebSocket처럼 헤더 커스터마이즈가
불가한 transport용으로 쿼리 파라미터 ?token=... 검증 dependency를 추가한다.
검증 로직은 get_current_user와 동일 (decode → token_type check → user lookup).

agent-user-context Design §6.1: get_auth_context Dependency 신설.
get_current_user 결과 + UserProfile + Department + Permission 합성 → AuthContext.
"""
import uuid

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.application.permission.assemble_auth_context import (
    AssembleAuthContextUseCase,
)
from src.domain.agent_run.auth_context import AuthContext
from src.domain.auth.entities import User
from src.domain.auth.interfaces import JWTAdapterInterface, UserRepositoryInterface

security = HTTPBearer()


def get_jwt_adapter() -> JWTAdapterInterface:
    """DI placeholder — overridden in create_app()."""
    raise NotImplementedError("JWTAdapterInterface not initialized")


def get_user_repository() -> UserRepositoryInterface:
    """DI placeholder — overridden in create_app()."""
    raise NotImplementedError("UserRepositoryInterface not initialized")


def get_assemble_auth_context_use_case() -> AssembleAuthContextUseCase:
    """DI placeholder — overridden in create_app()."""
    raise NotImplementedError("AssembleAuthContextUseCase not initialized")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    jwt_adapter: JWTAdapterInterface = Depends(get_jwt_adapter),
    user_repo: UserRepositoryInterface = Depends(get_user_repository),
) -> User:
    """Bearer 토큰에서 현재 사용자 추출."""
    try:
        payload = jwt_adapter.decode(credentials.credentials)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    if payload.token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token type mismatch",
        )

    user = await user_repo.find_by_id(int(payload.sub))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


def require_role(*roles: str):
    """RBAC Dependency — 사용법: Depends(require_role('admin'))"""
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role.value not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user
    return _check


async def get_auth_context(
    current_user: User = Depends(get_current_user),
    assemble_uc: AssembleAuthContextUseCase = Depends(
        get_assemble_auth_context_use_case
    ),
) -> AuthContext:
    """현재 요청의 AuthContext를 조립한다 (agent-user-context Design §6.1).

    - get_current_user 결과를 받아 UserProfile + Department + Permission 합성.
    - 매 요청마다 DB round-trip 3회 — p95 측정 후 캐싱 도입 검토.
    """
    request_id = str(uuid.uuid4())
    return await assemble_uc.execute(current_user, request_id)


async def get_auth_context_from_query_token(
    current_user: User = Depends(lambda: None),  # placeholder, real wired in main
    assemble_uc: AssembleAuthContextUseCase = Depends(
        get_assemble_auth_context_use_case
    ),
) -> AuthContext:
    """SSE/WS용 AuthContext Dependency.

    실제 wiring은 main.py에서 get_current_user_from_query_token으로 대체.
    """
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthenticated",
        )
    return await assemble_uc.execute(current_user, str(uuid.uuid4()))


async def get_current_user_from_query_token(
    token: str = Query(..., description="JWT access token (SSE/WS 전용)"),
    jwt_adapter: JWTAdapterInterface = Depends(get_jwt_adapter),
    user_repo: UserRepositoryInterface = Depends(get_user_repository),
) -> User:
    """쿼리 파라미터 ?token=... 기반 JWT 검증 (SSE/WebSocket용).

    EventSource API는 커스텀 헤더를 보낼 수 없으므로 쿼리에서 토큰을 받는다.
    검증 로직은 get_current_user와 동일하다.
    """
    try:
        payload = jwt_adapter.decode(token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    if payload.token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token type mismatch",
        )

    user = await user_repo.find_by_id(int(payload.sub))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user
