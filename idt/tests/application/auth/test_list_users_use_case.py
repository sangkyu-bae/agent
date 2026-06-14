"""ListUsersUseCase tests — 의존성 Mock.

admin-user-registration Design §4.2, §9.1.
"""
from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.application.auth.list_users_use_case import ListUsersUseCase
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.auth.interfaces import UserListFilters
from src.domain.department.entity import Department, UserDepartment
from src.domain.user_profile.entity import UserProfile


@pytest.fixture
def mock_user_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_profile_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_dept_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def use_case(mock_user_repo, mock_profile_repo, mock_dept_repo) -> ListUsersUseCase:
    return ListUsersUseCase(
        user_repo=mock_user_repo,
        user_profile_repo=mock_profile_repo,
        department_repo=mock_dept_repo,
        logger=MagicMock(),
    )


def _user(uid, email, role="user", status="approved"):
    return User(id=uid, email=email, password_hash="h",
                role=UserRole(role), status=UserStatus(status),
                created_at=datetime(2026, 5, 1, tzinfo=timezone.utc))


def _profile(uid, name, position=None):
    now = datetime.now(timezone.utc)
    return UserProfile(user_id=uid, display_name=name, position=position,
                       employee_no=None, joined_at=None,
                       created_at=now, updated_at=now)


class TestListUsersUseCase:
    @pytest.mark.asyncio
    async def test_combines_profile_and_department_names(
        self, use_case, mock_user_repo, mock_profile_repo, mock_dept_repo
    ) -> None:
        mock_user_repo.find_all.return_value = ([_user(1, "a@b.com")], 1)
        mock_profile_repo.find_by_user_id.return_value = _profile(1, "배상규", "대리")
        mock_dept_repo.list_all.return_value = [
            Department(id="d1", name="여신팀", description=None,
                       created_at=None, updated_at=None),
        ]
        mock_dept_repo.find_departments_by_user.return_value = [
            UserDepartment(user_id=1, department_id="d1", is_primary=True,
                           created_at=datetime.now(timezone.utc)),
        ]

        result = await use_case.execute(UserListFilters(), request_id="r")

        assert result.total == 1
        item = result.items[0]
        assert item.display_name == "배상규"
        assert item.position == "대리"
        assert item.department_names == ["여신팀"]
        assert item.status == "approved"

    @pytest.mark.asyncio
    async def test_profile_missing_yields_none(
        self, use_case, mock_user_repo, mock_profile_repo, mock_dept_repo
    ) -> None:
        mock_user_repo.find_all.return_value = ([_user(2, "c@b.com")], 1)
        mock_profile_repo.find_by_user_id.return_value = None
        mock_dept_repo.list_all.return_value = []
        mock_dept_repo.find_departments_by_user.return_value = []

        result = await use_case.execute(UserListFilters(), request_id="r")

        item = result.items[0]
        assert item.display_name is None
        assert item.department_names == []

    @pytest.mark.asyncio
    async def test_empty_list(
        self, use_case, mock_user_repo, mock_dept_repo
    ) -> None:
        mock_user_repo.find_all.return_value = ([], 0)
        mock_dept_repo.list_all.return_value = []

        result = await use_case.execute(UserListFilters(status=UserStatus.APPROVED), request_id="r")

        assert result.items == []
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_passes_filters_to_repo(
        self, use_case, mock_user_repo, mock_dept_repo
    ) -> None:
        mock_user_repo.find_all.return_value = ([], 0)
        mock_dept_repo.list_all.return_value = []
        filters = UserListFilters(status=UserStatus.PENDING, query="abc", limit=5, offset=10)

        await use_case.execute(filters, request_id="r")

        called_filters = mock_user_repo.find_all.call_args.args[0]
        assert called_filters.status == UserStatus.PENDING
        assert called_filters.query == "abc"
        assert called_filters.limit == 5
        assert called_filters.offset == 10
