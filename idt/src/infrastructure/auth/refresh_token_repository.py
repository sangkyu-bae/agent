"""RefreshTokenRepository: MySQL implementation."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.auth.interfaces import RefreshTokenRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.auth.models import RefreshTokenModel


class RefreshTokenRepository(RefreshTokenRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(self, user_id: int, token_hash: str, expires_at: datetime) -> None:
        model = RefreshTokenModel(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.commit()
        self._logger.info("RefreshToken saved", user_id=user_id)

    async def find_valid(self, token_hash: str) -> Optional[dict]:
        """유효한(만료되지 않고 revoke되지 않은) 토큰 레코드 반환."""
        now = datetime.now(timezone.utc)
        result = await self._session.execute(
            select(RefreshTokenModel).where(
                RefreshTokenModel.token_hash == token_hash,
                RefreshTokenModel.revoked_at.is_(None),
                RefreshTokenModel.expires_at > now,
            )
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return {
            "user_id": model.user_id,
            "expires_at": model.expires_at,
            "revoked_at": model.revoked_at,
        }

    async def revoke(self, token_hash: str) -> None:
        now = datetime.now(timezone.utc)
        await self._session.execute(
            update(RefreshTokenModel)
            .where(
                RefreshTokenModel.token_hash == token_hash,
                RefreshTokenModel.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        await self._session.commit()
        self._logger.info("RefreshToken revoked", token_hash=token_hash[:8] + "...")
