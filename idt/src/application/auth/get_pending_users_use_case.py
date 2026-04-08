"""GetPendingUsers UseCase (admin)."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from src.domain.auth.entities import UserStatus
from src.domain.auth.interfaces import UserRepositoryInterface
from src.domain.logging.interfaces import LoggerInterface


@dataclass
class PendingUserResult:
    id: int
    email: str
    role: str
    created_at: Optional[datetime]


class GetPendingUsersUseCase:
    def __init__(self, user_repo: UserRepositoryInterface, logger: LoggerInterface) -> None:
        self._user_repo = user_repo
        self._logger = logger

    async def execute(self, request_id: str) -> list[PendingUserResult]:
        self._logger.info("Get pending users", request_id=request_id)
        users = await self._user_repo.find_by_status(UserStatus.PENDING)
        return [
            PendingUserResult(id=u.id, email=u.email, role=u.role.value, created_at=u.created_at)
            for u in users
        ]
