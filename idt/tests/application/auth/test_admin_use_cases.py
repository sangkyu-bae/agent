"""Admin UseCases tests (get_pending, approve, reject)."""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from src.application.auth.get_pending_users_use_case import GetPendingUsersUseCase
from src.application.auth.approve_user_use_case import ApproveUserRequest, ApproveUserUseCase
from src.application.auth.reject_user_use_case import RejectUserRequest, RejectUserUseCase
from src.domain.auth.entities import User, UserStatus


@pytest.fixture
def user_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def logger() -> MagicMock:
    return MagicMock()


class TestGetPendingUsersUseCase:
    @pytest.mark.asyncio
    async def test_returns_pending_users(self, user_repo: AsyncMock, logger: MagicMock) -> None:
        user_repo.find_by_status.return_value = [
            User(id=1, email="a@b.com", password_hash="h", status=UserStatus.PENDING, created_at=datetime.now(timezone.utc)),
        ]
        uc = GetPendingUsersUseCase(user_repo=user_repo, logger=logger)
        result = await uc.execute("req-1")
        assert len(result) == 1
        assert result[0].email == "a@b.com"

    @pytest.mark.asyncio
    async def test_returns_empty_list(self, user_repo: AsyncMock, logger: MagicMock) -> None:
        user_repo.find_by_status.return_value = []
        uc = GetPendingUsersUseCase(user_repo=user_repo, logger=logger)
        result = await uc.execute("req-2")
        assert result == []


class TestApproveUserUseCase:
    @pytest.mark.asyncio
    async def test_approve_success(self, user_repo: AsyncMock, logger: MagicMock) -> None:
        user_repo.find_by_id.return_value = User(id=5, email="x@x.com", password_hash="h")
        uc = ApproveUserUseCase(user_repo=user_repo, logger=logger)
        await uc.execute(ApproveUserRequest(user_id=5), "req-1")
        user_repo.update_status.assert_called_once_with(5, UserStatus.APPROVED)

    @pytest.mark.asyncio
    async def test_approve_user_not_found_raises(self, user_repo: AsyncMock, logger: MagicMock) -> None:
        user_repo.find_by_id.return_value = None
        uc = ApproveUserUseCase(user_repo=user_repo, logger=logger)
        with pytest.raises(ValueError, match="User not found"):
            await uc.execute(ApproveUserRequest(user_id=999), "req-2")

    @pytest.mark.asyncio
    async def test_approve_already_approved_is_idempotent(self, user_repo: AsyncMock, logger: MagicMock) -> None:
        user_repo.find_by_id.return_value = User(id=5, email="x@x.com", password_hash="h", status=UserStatus.APPROVED)
        uc = ApproveUserUseCase(user_repo=user_repo, logger=logger)
        await uc.execute(ApproveUserRequest(user_id=5), "req-3")
        user_repo.update_status.assert_not_called()


class TestRejectUserUseCase:
    @pytest.mark.asyncio
    async def test_reject_success(self, user_repo: AsyncMock, logger: MagicMock) -> None:
        user_repo.find_by_id.return_value = User(id=6, email="y@y.com", password_hash="h")
        uc = RejectUserUseCase(user_repo=user_repo, logger=logger)
        await uc.execute(RejectUserRequest(user_id=6), "req-1")
        user_repo.update_status.assert_called_once_with(6, UserStatus.REJECTED)

    @pytest.mark.asyncio
    async def test_reject_user_not_found_raises(self, user_repo: AsyncMock, logger: MagicMock) -> None:
        user_repo.find_by_id.return_value = None
        uc = RejectUserUseCase(user_repo=user_repo, logger=logger)
        with pytest.raises(ValueError, match="User not found"):
            await uc.execute(RejectUserRequest(user_id=999), "req-2")
