"""UserRepository: MySQL implementation."""
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.auth.interfaces import UserRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.auth.models import UserModel


def _to_entity(model: UserModel) -> User:
    return User(
        id=model.id,
        email=model.email,
        password_hash=model.password_hash,
        role=UserRole(model.role),
        status=UserStatus(model.status),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class UserRepository(UserRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(self, user: User) -> User:
        model = UserModel(
            email=user.email,
            password_hash=user.password_hash,
            role=user.role.value,
            status=user.status.value,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        await self._session.commit()
        self._logger.info("User saved", user_id=model.id)
        return _to_entity(model)

    async def find_by_email(self, email: str) -> Optional[User]:
        result = await self._session.execute(
            select(UserModel).where(UserModel.email == email)
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None

    async def find_by_id(self, user_id: int) -> Optional[User]:
        result = await self._session.execute(
            select(UserModel).where(UserModel.id == user_id)
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None

    async def find_by_status(self, status: UserStatus) -> list[User]:
        result = await self._session.execute(
            select(UserModel).where(UserModel.status == status.value)
        )
        return [_to_entity(m) for m in result.scalars().all()]

    async def update_status(self, user_id: int, status: UserStatus) -> None:
        await self._session.execute(
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(status=status.value)
        )
        await self._session.commit()
        self._logger.info("User status updated", user_id=user_id, status=status.value)
