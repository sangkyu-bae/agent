"""ApproveUser UseCase (admin)."""
from dataclasses import dataclass

from src.domain.auth.entities import UserStatus
from src.domain.auth.interfaces import UserRepositoryInterface
from src.domain.logging.interfaces import LoggerInterface


@dataclass
class ApproveUserRequest:
    user_id: int


class ApproveUserUseCase:
    def __init__(self, user_repo: UserRepositoryInterface, logger: LoggerInterface) -> None:
        self._user_repo = user_repo
        self._logger = logger

    async def execute(self, request: ApproveUserRequest, request_id: str) -> None:
        self._logger.info("Approve user", request_id=request_id, user_id=request.user_id)
        user = await self._user_repo.find_by_id(request.user_id)
        if not user:
            raise ValueError("User not found")
        if user.status == UserStatus.APPROVED:
            return  # 멱등성
        await self._user_repo.update_status(request.user_id, UserStatus.APPROVED)
        self._logger.info("User approved", request_id=request_id, user_id=request.user_id)
