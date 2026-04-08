"""UserRepository tests (AsyncSession mock 사용)."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.domain.auth.entities import User, UserRole, UserStatus
from src.infrastructure.auth.user_repository import UserRepository
from src.infrastructure.auth.models import UserModel


def _make_repo(session=None, logger=None):
    session = session or AsyncMock()
    logger = logger or MagicMock()
    return UserRepository(session=session, logger=logger), session, logger


def _make_user_model(
    id: int = 1,
    email: str = "a@b.com",
    role: str = "user",
    status: str = "pending",
) -> MagicMock:
    model = MagicMock(spec=UserModel)
    model.id = id
    model.email = email
    model.password_hash = "hashed"
    model.role = role
    model.status = status
    model.created_at = None
    model.updated_at = None
    return model


def _mock_scalar_one_or_none(session: AsyncMock, value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    session.execute = AsyncMock(return_value=result)


def _mock_scalars_all(session: AsyncMock, values: list):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    session.execute = AsyncMock(return_value=result)


class TestUserRepositorySave:
    @pytest.mark.asyncio
    async def test_save_adds_and_returns_entity(self) -> None:
        repo, session, _ = _make_repo()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        user_input = User(email="new@example.com", password_hash="hashed_pw")

        # refresh 호출 시 model.id가 채워지도록 side_effect 설정
        def _set_id(model):
            model.id = 10
            model.email = "new@example.com"
            model.password_hash = "hashed_pw"
            model.role = "user"
            model.status = "pending"
            model.created_at = None
            model.updated_at = None

        session.refresh.side_effect = _set_id

        result = await repo.save(user_input)

        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once()
        assert result.id == 10
        assert result.email == "new@example.com"


class TestUserRepositoryFindByEmail:
    @pytest.mark.asyncio
    async def test_find_existing_email_returns_entity(self) -> None:
        repo, session, _ = _make_repo()
        _mock_scalar_one_or_none(session, _make_user_model(id=1, email="a@b.com"))

        result = await repo.find_by_email("a@b.com")

        assert result is not None
        assert result.email == "a@b.com"
        assert result.role == UserRole.USER

    @pytest.mark.asyncio
    async def test_find_missing_email_returns_none(self) -> None:
        repo, session, _ = _make_repo()
        _mock_scalar_one_or_none(session, None)

        result = await repo.find_by_email("notfound@b.com")

        assert result is None


class TestUserRepositoryFindById:
    @pytest.mark.asyncio
    async def test_find_existing_id_returns_entity(self) -> None:
        repo, session, _ = _make_repo()
        _mock_scalar_one_or_none(session, _make_user_model(id=42))

        result = await repo.find_by_id(42)

        assert result is not None
        assert result.id == 42

    @pytest.mark.asyncio
    async def test_find_missing_id_returns_none(self) -> None:
        repo, session, _ = _make_repo()
        _mock_scalar_one_or_none(session, None)

        result = await repo.find_by_id(999)

        assert result is None


class TestUserRepositoryFindByStatus:
    @pytest.mark.asyncio
    async def test_find_pending_users(self) -> None:
        repo, session, _ = _make_repo()
        _mock_scalars_all(session, [
            _make_user_model(id=1, status="pending"),
            _make_user_model(id=2, email="b@b.com", status="pending"),
        ])

        result = await repo.find_by_status(UserStatus.PENDING)

        assert len(result) == 2
        assert all(u.status == UserStatus.PENDING for u in result)

    @pytest.mark.asyncio
    async def test_find_no_pending_returns_empty(self) -> None:
        repo, session, _ = _make_repo()
        _mock_scalars_all(session, [])

        result = await repo.find_by_status(UserStatus.PENDING)

        assert result == []


class TestUserRepositoryUpdateStatus:
    @pytest.mark.asyncio
    async def test_update_status_executes_update(self) -> None:
        repo, session, _ = _make_repo()
        result_mock = MagicMock()
        session.execute = AsyncMock(return_value=result_mock)

        await repo.update_status(1, UserStatus.APPROVED)

        session.execute.assert_awaited_once()
