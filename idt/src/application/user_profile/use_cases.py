"""UserProfile UseCase — Get/Update.

agent-user-context Design §4.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.user_profile.entity import UserProfile
from src.domain.user_profile.interfaces import UserProfileRepositoryInterface


@dataclass
class UpsertUserProfileRequest:
    user_id: int
    display_name: str
    position: str | None = None
    employee_no: str | None = None
    joined_at: date | None = None


class GetUserProfileUseCase:
    def __init__(
        self,
        profile_repo: UserProfileRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._profile_repo = profile_repo
        self._logger = logger

    async def execute(
        self, user_id: int, request_id: str
    ) -> UserProfile | None:
        return await self._profile_repo.find_by_user_id(user_id, request_id)


class UpsertUserProfileUseCase:
    def __init__(
        self,
        profile_repo: UserProfileRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._profile_repo = profile_repo
        self._logger = logger

    async def execute(
        self, req: UpsertUserProfileRequest, request_id: str
    ) -> UserProfile:
        now = datetime.now(timezone.utc)
        profile = UserProfile(
            user_id=req.user_id,
            display_name=req.display_name,
            position=req.position,
            employee_no=req.employee_no,
            joined_at=req.joined_at,
            created_at=now,   # upsert 시 무시됨 — DB가 우선 (Repository 참조)
            updated_at=now,
        )
        return await self._profile_repo.upsert(profile, request_id)
