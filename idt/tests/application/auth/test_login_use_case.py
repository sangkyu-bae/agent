"""LoginUseCase tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.application.auth.login_use_case import LoginRequest, LoginUseCase
from src.domain.auth.entities import User, UserStatus


@pytest.fixture
def approved_user() -> User:
    return User(id=1, email="ok@example.com", password_hash="hashed", status=UserStatus.APPROVED)


@pytest.fixture
def mocks() -> dict:
    return {
        "user_repo": AsyncMock(),
        "rt_repo": AsyncMock(),
        "hasher": MagicMock(),
        "jwt": MagicMock(),
        "logger": MagicMock(),
    }


@pytest.fixture
def use_case(mocks: dict) -> LoginUseCase:
    return LoginUseCase(
        user_repo=mocks["user_repo"],
        refresh_token_repo=mocks["rt_repo"],
        password_hasher=mocks["hasher"],
        jwt_adapter=mocks["jwt"],
        logger=mocks["logger"],
    )


class TestLoginUseCase:
    @pytest.mark.asyncio
    async def test_login_success(self, use_case: LoginUseCase, mocks: dict, approved_user: User) -> None:
        mocks["user_repo"].find_by_email.return_value = approved_user
        mocks["hasher"].verify.return_value = True
        mocks["jwt"].create_access_token.return_value = "access"
        mocks["jwt"].create_refresh_token.return_value = "refresh"
        mocks["jwt"].hash_token.return_value = "hashed_rt"

        result = await use_case.execute(LoginRequest(email="ok@example.com", password="pw"), "req-1")

        assert result.access_token == "access"
        assert result.refresh_token == "refresh"
        mocks["rt_repo"].save.assert_called_once()

    @pytest.mark.asyncio
    async def test_login_user_not_found_raises(self, use_case: LoginUseCase, mocks: dict) -> None:
        mocks["user_repo"].find_by_email.return_value = None
        with pytest.raises(ValueError, match="Invalid credentials"):
            await use_case.execute(LoginRequest(email="x@x.com", password="pw"), "req-2")

    @pytest.mark.asyncio
    async def test_login_pending_raises(self, use_case: LoginUseCase, mocks: dict) -> None:
        mocks["user_repo"].find_by_email.return_value = User(
            id=2, email="p@p.com", password_hash="h", status=UserStatus.PENDING
        )
        with pytest.raises(ValueError, match="pending approval"):
            await use_case.execute(LoginRequest(email="p@p.com", password="pw"), "req-3")

    @pytest.mark.asyncio
    async def test_login_rejected_raises(self, use_case: LoginUseCase, mocks: dict) -> None:
        mocks["user_repo"].find_by_email.return_value = User(
            id=3, email="r@r.com", password_hash="h", status=UserStatus.REJECTED
        )
        with pytest.raises(ValueError, match="rejected"):
            await use_case.execute(LoginRequest(email="r@r.com", password="pw"), "req-4")

    @pytest.mark.asyncio
    async def test_login_wrong_password_raises(self, use_case: LoginUseCase, mocks: dict, approved_user: User) -> None:
        mocks["user_repo"].find_by_email.return_value = approved_user
        mocks["hasher"].verify.return_value = False
        with pytest.raises(ValueError, match="Invalid credentials"):
            await use_case.execute(LoginRequest(email="ok@example.com", password="wrong"), "req-5")
