"""RegisterUseCase tests — 의존성 Mock."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.application.auth.register_use_case import RegisterRequest, RegisterUseCase
from src.domain.auth.entities import User, UserRole, UserStatus


@pytest.fixture
def mock_user_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_hasher() -> MagicMock:
    m = MagicMock()
    m.hash.return_value = "hashed_pw"
    return m


@pytest.fixture
def mock_logger() -> MagicMock:
    return MagicMock()


@pytest.fixture
def use_case(mock_user_repo: AsyncMock, mock_hasher: MagicMock, mock_logger: MagicMock) -> RegisterUseCase:
    return RegisterUseCase(
        user_repo=mock_user_repo,
        password_hasher=mock_hasher,
        logger=mock_logger,
    )


class TestRegisterUseCase:
    @pytest.mark.asyncio
    async def test_register_success(
        self, use_case: RegisterUseCase, mock_user_repo: AsyncMock, mock_hasher: MagicMock
    ) -> None:
        mock_user_repo.find_by_email.return_value = None
        mock_user_repo.save.return_value = User(
            id=1, email="new@example.com", password_hash="hashed_pw"
        )

        result = await use_case.execute(
            RegisterRequest(email="new@example.com", password="secure1234"),
            request_id="req-1",
        )

        assert result.user_id == 1
        assert result.email == "new@example.com"
        assert result.status == "pending"
        mock_hasher.hash.assert_called_once_with("secure1234")

    @pytest.mark.asyncio
    async def test_register_duplicate_email_raises(
        self, use_case: RegisterUseCase, mock_user_repo: AsyncMock
    ) -> None:
        mock_user_repo.find_by_email.return_value = User(
            email="dup@example.com", password_hash="hash"
        )

        with pytest.raises(ValueError, match="already registered"):
            await use_case.execute(
                RegisterRequest(email="dup@example.com", password="secure1234"),
                request_id="req-2",
            )

    @pytest.mark.asyncio
    async def test_register_invalid_email_raises(
        self, use_case: RegisterUseCase
    ) -> None:
        with pytest.raises(ValueError):
            await use_case.execute(
                RegisterRequest(email="not-an-email", password="secure1234"),
                request_id="req-3",
            )

    @pytest.mark.asyncio
    async def test_register_short_password_raises(
        self, use_case: RegisterUseCase, mock_user_repo: AsyncMock
    ) -> None:
        mock_user_repo.find_by_email.return_value = None

        with pytest.raises(ValueError, match="at least"):
            await use_case.execute(
                RegisterRequest(email="ok@example.com", password="short"),
                request_id="req-4",
            )
