"""UserProfileRepository — user_profiles MySQL CRUD.

agent-user-context Design §5.3.
- docs/rules/db-session.md 준수: commit은 dependency가 담당, flush까지만.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.user_profile.entity import UserProfile
from src.domain.user_profile.interfaces import UserProfileRepositoryInterface
from src.infrastructure.user_profile.models import UserProfileModel


def _to_domain(model: UserProfileModel) -> UserProfile:
    return UserProfile(
        user_id=model.user_id,
        display_name=model.display_name,
        position=model.position,
        employee_no=model.employee_no,
        joined_at=model.joined_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class UserProfileRepository(UserProfileRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def find_by_user_id(
        self, user_id: int, request_id: str
    ) -> UserProfile | None:
        self._logger.info(
            "UserProfile find_by_user_id", request_id=request_id, user_id=user_id,
        )
        try:
            stmt = select(UserProfileModel).where(
                UserProfileModel.user_id == user_id
            )
            result = await self._session.execute(stmt)
            model = result.scalar_one_or_none()
            return _to_domain(model) if model else None
        except Exception as e:
            self._logger.error(
                "UserProfile find_by_user_id failed",
                exception=e, request_id=request_id,
            )
            raise

    async def upsert(
        self, profile: UserProfile, request_id: str
    ) -> UserProfile:
        """MySQL ON DUPLICATE KEY UPDATE 기반 upsert.

        PK=user_id 충돌 시 display_name/position/employee_no/joined_at만 갱신.
        created_at/updated_at은 DB 트리거에 위임.
        """
        self._logger.info(
            "UserProfile upsert", request_id=request_id, user_id=profile.user_id,
        )
        try:
            now = datetime.now(timezone.utc)
            stmt = mysql_insert(UserProfileModel).values(
                user_id=profile.user_id,
                display_name=profile.display_name,
                position=profile.position,
                employee_no=profile.employee_no,
                joined_at=profile.joined_at,
                created_at=now,
                updated_at=now,
            )
            stmt = stmt.on_duplicate_key_update(
                display_name=stmt.inserted.display_name,
                position=stmt.inserted.position,
                employee_no=stmt.inserted.employee_no,
                joined_at=stmt.inserted.joined_at,
                updated_at=now,
            )
            await self._session.execute(stmt)
            await self._session.flush()
            # 재조회 — DB에서 실제 created_at/updated_at 가져옴
            refreshed = await self.find_by_user_id(profile.user_id, request_id)
            return refreshed if refreshed else profile
        except Exception as e:
            self._logger.error(
                "UserProfile upsert failed",
                exception=e, request_id=request_id,
            )
            raise
