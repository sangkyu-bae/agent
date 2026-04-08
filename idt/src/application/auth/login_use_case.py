"""Login UseCase."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.domain.auth.entities import UserStatus
from src.domain.auth.interfaces import (
    JWTAdapterInterface,
    PasswordHasherInterface,
    RefreshTokenRepositoryInterface,
    UserRepositoryInterface,
)
from src.domain.logging.interfaces import LoggerInterface


@dataclass
class LoginRequest:
    email: str
    password: str


@dataclass
class LoginResult:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginUseCase:
    def __init__(
        self,
        user_repo: UserRepositoryInterface,
        refresh_token_repo: RefreshTokenRepositoryInterface,
        password_hasher: PasswordHasherInterface,
        jwt_adapter: JWTAdapterInterface,
        logger: LoggerInterface,
    ) -> None:
        self._user_repo = user_repo
        self._rt_repo = refresh_token_repo
        self._hasher = password_hasher
        self._jwt = jwt_adapter
        self._logger = logger

    async def execute(self, request: LoginRequest, request_id: str) -> LoginResult:
        self._logger.info("Login attempt", request_id=request_id, email=request.email)

        user = await self._user_repo.find_by_email(request.email)
        if not user:
            raise ValueError("Invalid credentials")

        if user.status == UserStatus.PENDING:
            raise ValueError("Account is pending approval")
        if user.status == UserStatus.REJECTED:
            raise ValueError("Account has been rejected")

        if not self._hasher.verify(request.password, user.password_hash):
            raise ValueError("Invalid credentials")

        access_token = self._jwt.create_access_token(user.id, user.role.value)
        refresh_token = self._jwt.create_refresh_token(user.id, user.role.value)
        token_hash = self._jwt.hash_token(refresh_token)

        payload = self._jwt.decode(refresh_token)
        expires_at = datetime.fromtimestamp(payload.exp, tz=timezone.utc)
        await self._rt_repo.save(user.id, token_hash, expires_at)

        self._logger.info("Login successful", request_id=request_id, user_id=user.id)
        return LoginResult(access_token=access_token, refresh_token=refresh_token)
