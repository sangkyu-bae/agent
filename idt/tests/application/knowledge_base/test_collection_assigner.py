from unittest.mock import AsyncMock

import pytest

from src.application.knowledge_base.collection_assigner import (
    UserSelectedCollectionAssigner,
)
from src.domain.auth.entities import User, UserRole, UserStatus


def _user(user_id: int = 1) -> User:
    return User(
        email="test@test.com",
        password_hash="hash",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=user_id,
    )


@pytest.fixture
def mock_collection_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.collection_exists.return_value = True
    return repo


@pytest.fixture
def mock_perm_service() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def assigner(
    mock_collection_repo: AsyncMock, mock_perm_service: AsyncMock
) -> UserSelectedCollectionAssigner:
    return UserSelectedCollectionAssigner(
        collection_repo=mock_collection_repo,
        perm_service=mock_perm_service,
    )


class TestAssign:
    async def test_returns_requested_collection(
        self, assigner, mock_perm_service
    ):
        result = await assigner.assign(_user(), "shared-col", "req-1")
        assert result == "shared-col"
        mock_perm_service.check_read_access.assert_awaited_once()

    async def test_missing_collection_name_raises(self, assigner):
        with pytest.raises(ValueError, match="required"):
            await assigner.assign(_user(), None, "req-1")

    async def test_empty_collection_name_raises(self, assigner):
        with pytest.raises(ValueError, match="required"):
            await assigner.assign(_user(), "", "req-1")

    async def test_nonexistent_collection_raises(
        self, assigner, mock_collection_repo
    ):
        mock_collection_repo.collection_exists.return_value = False
        with pytest.raises(ValueError, match="not found"):
            await assigner.assign(_user(), "ghost", "req-1")

    async def test_no_read_access_propagates_permission_error(
        self, assigner, mock_perm_service
    ):
        mock_perm_service.check_read_access.side_effect = PermissionError(
            "No read access"
        )
        with pytest.raises(PermissionError):
            await assigner.assign(_user(), "secret-col", "req-1")
