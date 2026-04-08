"""Refresh + Logout UseCase tests."""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from src.application.auth.refresh_token_use_case import RefreshTokenRequest, RefreshTokenUseCase
from src.application.auth.logout_use_case import LogoutRequest, LogoutUseCase
from src.domain.auth.value_objects import TokenPayload


@pytest.fixture
def jwt_mock() -> MagicMock:
    m = MagicMock()
    m.hash_token.return_value = "hashed_rt"
    return m


@pytest.fixture
def rt_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def logger() -> MagicMock:
    return MagicMock()


class TestRefreshTokenUseCase:
    @pytest.mark.asyncio
    async def test_refresh_success(self, jwt_mock: MagicMock, rt_repo: AsyncMock, logger: MagicMock) -> None:
        jwt_mock.decode.return_value = TokenPayload(sub="1", role="user", token_type="refresh", exp=9999999999)
        rt_repo.find_valid.return_value = {"user_id": 1, "expires_at": datetime.now(timezone.utc), "revoked_at": None}
        jwt_mock.create_access_token.return_value = "new_access"

        uc = RefreshTokenUseCase(rt_repo=rt_repo, jwt_adapter=jwt_mock, logger=logger)
        result = await uc.execute(RefreshTokenRequest(refresh_token="old_rt"), "req-1")

        assert result.access_token == "new_access"

    @pytest.mark.asyncio
    async def test_refresh_wrong_token_type_raises(self, jwt_mock: MagicMock, rt_repo: AsyncMock, logger: MagicMock) -> None:
        jwt_mock.decode.return_value = TokenPayload(sub="1", role="user", token_type="access", exp=9999999999)

        uc = RefreshTokenUseCase(rt_repo=rt_repo, jwt_adapter=jwt_mock, logger=logger)
        with pytest.raises(ValueError, match="Token type mismatch"):
            await uc.execute(RefreshTokenRequest(refresh_token="bad_rt"), "req-2")

    @pytest.mark.asyncio
    async def test_refresh_revoked_token_raises(self, jwt_mock: MagicMock, rt_repo: AsyncMock, logger: MagicMock) -> None:
        jwt_mock.decode.return_value = TokenPayload(sub="1", role="user", token_type="refresh", exp=9999999999)
        rt_repo.find_valid.return_value = None

        uc = RefreshTokenUseCase(rt_repo=rt_repo, jwt_adapter=jwt_mock, logger=logger)
        with pytest.raises(ValueError, match="Invalid or expired"):
            await uc.execute(RefreshTokenRequest(refresh_token="revoked"), "req-3")


class TestLogoutUseCase:
    @pytest.mark.asyncio
    async def test_logout_success(self, jwt_mock: MagicMock, rt_repo: AsyncMock, logger: MagicMock) -> None:
        uc = LogoutUseCase(rt_repo=rt_repo, jwt_adapter=jwt_mock, logger=logger)
        await uc.execute(LogoutRequest(refresh_token="rt"), "req-1")
        rt_repo.revoke.assert_called_once_with("hashed_rt")

    @pytest.mark.asyncio
    async def test_logout_idempotent(self, jwt_mock: MagicMock, rt_repo: AsyncMock, logger: MagicMock) -> None:
        # revoke를 두 번 호출해도 예외 없음
        uc = LogoutUseCase(rt_repo=rt_repo, jwt_adapter=jwt_mock, logger=logger)
        await uc.execute(LogoutRequest(refresh_token="rt"), "req-1")
        await uc.execute(LogoutRequest(refresh_token="rt"), "req-2")
        assert rt_repo.revoke.call_count == 2
