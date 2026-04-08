"""RejectUser UseCase (admin)."""
from dataclasses import dataclass

from src.domain.auth.entities import UserStatus
from src.domain.auth.interfaces import UserRepositoryInterface
from src.domain.logging.interfaces import LoggerInterface


@dataclass
class RejectUserRequest:
    user_id: int


class RejectUserUseCase:
    def __init__(self, user_repo: UserRepositoryInterface, logger: LoggerInterface) -> None:
        self._user_repo = user_repo
        self._logger = logger

    async def execute(self, request: RejectUserRequest, request_id: str) -> None:
        self._logger.info("Reject user", request_id=request_id, user_id=request.user_id)
        user = await self._user_repo.find_by_id(request.user_id)
        if not user:
            raise ValueError("User not found")
        await self._user_repo.update_status(request.user_id, UserStatus.REJECTED)
        self._logger.info("User rejected", request_id=request_id, user_id=request.user_id)
