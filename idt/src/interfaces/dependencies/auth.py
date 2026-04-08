"""FastAPI auth dependencies (get_current_user, require_role)."""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.domain.auth.entities import User
from src.domain.auth.interfaces import JWTAdapterInterface, UserRepositoryInterface

security = HTTPBearer()


def get_jwt_adapter() -> JWTAdapterInterface:
    """DI placeholder — overridden in create_app()."""
    raise NotImplementedError("JWTAdapterInterface not initialized")


def get_user_repository() -> UserRepositoryInterface:
    """DI placeholder — overridden in create_app()."""
    raise NotImplementedError("UserRepositoryInterface not initialized")


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
