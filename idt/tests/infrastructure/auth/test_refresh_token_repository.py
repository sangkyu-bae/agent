"""RefreshTokenRepository tests (AsyncSession mock 사용)."""
from datetime import datetime, timedelta, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.infrastructure.auth.refresh_token_repository import RefreshTokenRepository
from src.infrastructure.auth.models import RefreshTokenModel


def _make_repo(session=None, logger=None):
    session = session or AsyncMock()
    logger = logger or MagicMock()
    return RefreshTokenRepository(session=session, logger=logger), session, logger


def _make_token_model(
    user_id: int = 1,
    token_hash: str = "abc123",
    expires_at: datetime = None,
    revoked_at: datetime = None,
) -> MagicMock:
    model = MagicMock(spec=RefreshTokenModel)
    model.user_id = user_id
    model.token_hash = token_hash
    model.expires_at = expires_at or (datetime.now(timezone.utc) + timedelta(days=7))
    model.revoked_at = revoked_at
    return model


def _mock_scalar_one_or_none(session: AsyncMock, value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    session.execute = AsyncMock(return_value=result)


class TestRefreshTokenRepositorySave:
    @pytest.mark.asyncio
    async def test_save_adds_model(self) -> None:
        repo, session, _ = _make_repo()
        session.flush = AsyncMock()
        expires = datetime.now(timezone.utc) + timedelta(days=7)

        await repo.save(user_id=1, token_hash="hash_abc", expires_at=expires)

        session.add.assert_called_once()
        session.flush.assert_awaited_once()


class TestRefreshTokenRepositoryFindValid:
    @pytest.mark.asyncio
    async def test_find_valid_existing_token_returns_dict(self) -> None:
        repo, session, _ = _make_repo()
        expires = datetime.now(timezone.utc) + timedelta(days=7)
        _mock_scalar_one_or_none(session, _make_token_model(user_id=3, expires_at=expires))

        result = await repo.find_valid("hash_abc")

        assert result is not None
        assert result["user_id"] == 3
        assert "expires_at" in result
        assert "revoked_at" in result

    @pytest.mark.asyncio
    async def test_find_valid_missing_token_returns_none(self) -> None:
        repo, session, _ = _make_repo()
        _mock_scalar_one_or_none(session, None)

        result = await repo.find_valid("nonexistent_hash")

        assert result is None


class TestRefreshTokenRepositoryRevoke:
    @pytest.mark.asyncio
    async def test_revoke_executes_update(self) -> None:
        repo, session, _ = _make_repo()
        result_mock = MagicMock()
        session.execute = AsyncMock(return_value=result_mock)

        await repo.revoke("hash_abc")

        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_revoke_already_revoked_is_idempotent(self) -> None:
        """이미 무효화된 토큰에 revoke 호출해도 오류 없이 통과."""
        repo, session, _ = _make_repo()
        result_mock = MagicMock()
        session.execute = AsyncMock(return_value=result_mock)

        await repo.revoke("hash_already_revoked")

        # 오류 없이 execute가 호출됨을 확인
        session.execute.assert_awaited_once()
