"""Refresh Token UseCase."""
from dataclasses import dataclass

from src.domain.auth.interfaces import JWTAdapterInterface, RefreshTokenRepositoryInterface
from src.domain.logging.interfaces import LoggerInterface


@dataclass
class RefreshTokenRequest:
    refresh_token: str


@dataclass
class RefreshTokenResult:
    access_token: str
    token_type: str = "bearer"


class RefreshTokenUseCase:
    def __init__(
        self,
        rt_repo: RefreshTokenRepositoryInterface,
        jwt_adapter: JWTAdapterInterface,
        logger: LoggerInterface,
    ) -> None:
        self._rt_repo = rt_repo
        self._jwt = jwt_adapter
        self._logger = logger

    async def execute(self, request: RefreshTokenRequest, request_id: str) -> RefreshTokenResult:
        self._logger.info("Refresh token attempt", request_id=request_id)

        payload = self._jwt.decode(request.refresh_token)
        if payload.token_type != "refresh":
            raise ValueError("Token type mismatch")

        token_hash = self._jwt.hash_token(request.refresh_token)
        record = await self._rt_repo.find_valid(token_hash)
        if not record:
            raise ValueError("Invalid or expired refresh token")

        access_token = self._jwt.create_access_token(int(payload.sub), payload.role)
        self._logger.info("Token refreshed", request_id=request_id)
        return RefreshTokenResult(access_token=access_token)
