"""Logout UseCase."""
from dataclasses import dataclass

from src.domain.auth.interfaces import JWTAdapterInterface, RefreshTokenRepositoryInterface
from src.domain.logging.interfaces import LoggerInterface


@dataclass
class LogoutRequest:
    refresh_token: str


class LogoutUseCase:
    def __init__(
        self,
        rt_repo: RefreshTokenRepositoryInterface,
        jwt_adapter: JWTAdapterInterface,
        logger: LoggerInterface,
    ) -> None:
        self._rt_repo = rt_repo
        self._jwt = jwt_adapter
        self._logger = logger

    async def execute(self, request: LogoutRequest, request_id: str) -> None:
        self._logger.info("Logout", request_id=request_id)
        token_hash = self._jwt.hash_token(request.refresh_token)
        await self._rt_repo.revoke(token_hash)
