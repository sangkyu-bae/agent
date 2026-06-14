"""AdminCreateUserUseCase tests — 의존성 Mock.

admin-user-registration Design §4.1, §9.1.
"""
from datetime import date

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.application.auth.admin_create_user_use_case import (
    AdminCreateUserCommand,
    AdminCreateUserUseCase,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.department.entity import Department


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
def mock_hasher() -> MagicMock:
    m = MagicMock()
    m.hash.return_value = "hashed_pw"
    return m


@pytest.fixture
def use_case(mock_user_repo, mock_profile_repo, mock_dept_repo, mock_hasher) -> AdminCreateUserUseCase:
    return AdminCreateUserUseCase(
        user_repo=mock_user_repo,
        user_profile_repo=mock_profile_repo,
        department_repo=mock_dept_repo,
        password_hasher=mock_hasher,
        logger=MagicMock(),
    )


def _saved_user(uid=1, email="new@example.com", role="user"):
    return User(id=uid, email=email, password_hash="hashed_pw",
                role=UserRole(role), status=UserStatus.APPROVED)


class TestAdminCreateUserUseCase:
    @pytest.mark.asyncio
    async def test_success_without_department(
        self, use_case, mock_user_repo, mock_profile_repo, mock_dept_repo, mock_hasher
    ) -> None:
        mock_user_repo.find_by_email.return_value = None
        mock_user_repo.save.return_value = _saved_user()

        result = await use_case.execute(
            AdminCreateUserCommand(
                email="new@example.com", password="secure1234",
                display_name="배상규", position="대리",
                employee_no="E1001", joined_at=date(2024, 1, 2), role="user",
            ),
            request_id="r1", created_by=99,
        )

        assert result.user_id == 1
        assert result.status == "approved"  # 즉시 활성
        assert result.display_name == "배상규"
        assert result.position == "대리"
        mock_hasher.hash.assert_called_once_with("secure1234")
        mock_profile_repo.upsert.assert_awaited_once()
        mock_dept_repo.assign_user.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_with_department(
        self, use_case, mock_user_repo, mock_profile_repo, mock_dept_repo
    ) -> None:
        mock_user_repo.find_by_email.return_value = None
        mock_user_repo.save.return_value = _saved_user()
        mock_dept_repo.find_by_id.return_value = Department(
            id="dept-1", name="여신팀", description=None,
            created_at=None, updated_at=None,
        )

        result = await use_case.execute(
            AdminCreateUserCommand(
                email="new@example.com", password="secure1234",
                display_name="배상규", role="user", department_id="dept-1",
            ),
            request_id="r2", created_by=99,
        )

        assert result.department_id == "dept-1"
        mock_dept_repo.find_by_id.assert_awaited_once()
        mock_dept_repo.assign_user.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_admin_role_allowed(
        self, use_case, mock_user_repo
    ) -> None:
        mock_user_repo.find_by_email.return_value = None
        mock_user_repo.save.return_value = _saved_user(role="admin")

        result = await use_case.execute(
            AdminCreateUserCommand(
                email="boss@example.com", password="secure1234",
                display_name="관리자", role="admin",
            ),
            request_id="r3", created_by=99,
        )
        assert result.role == "admin"

    @pytest.mark.asyncio
    async def test_duplicate_email_raises(self, use_case, mock_user_repo) -> None:
        mock_user_repo.find_by_email.return_value = _saved_user()

        with pytest.raises(ValueError, match="already registered"):
            await use_case.execute(
                AdminCreateUserCommand(
                    email="dup@example.com", password="secure1234", display_name="x",
                ),
                request_id="r4", created_by=99,
            )

    @pytest.mark.asyncio
    async def test_short_password_raises(self, use_case, mock_user_repo) -> None:
        mock_user_repo.find_by_email.return_value = None
        with pytest.raises(ValueError, match="at least"):
            await use_case.execute(
                AdminCreateUserCommand(
                    email="ok@example.com", password="short", display_name="x",
                ),
                request_id="r5", created_by=99,
            )

    @pytest.mark.asyncio
    async def test_blank_display_name_raises(self, use_case, mock_user_repo) -> None:
        mock_user_repo.find_by_email.return_value = None
        with pytest.raises(ValueError, match="display_name"):
            await use_case.execute(
                AdminCreateUserCommand(
                    email="ok@example.com", password="secure1234", display_name="   ",
                ),
                request_id="r6", created_by=99,
            )

    @pytest.mark.asyncio
    async def test_invalid_role_raises(self, use_case, mock_user_repo) -> None:
        mock_user_repo.find_by_email.return_value = None
        with pytest.raises(ValueError):
            await use_case.execute(
                AdminCreateUserCommand(
                    email="ok@example.com", password="secure1234",
                    display_name="x", role="superuser",
                ),
                request_id="r7", created_by=99,
            )

    @pytest.mark.asyncio
    async def test_unknown_department_raises(
        self, use_case, mock_user_repo, mock_dept_repo
    ) -> None:
        mock_user_repo.find_by_email.return_value = None
        mock_user_repo.save.return_value = _saved_user()
        mock_dept_repo.find_by_id.return_value = None  # 없는 부서

        with pytest.raises(ValueError, match="부서"):
            await use_case.execute(
                AdminCreateUserCommand(
                    email="new@example.com", password="secure1234",
                    display_name="x", department_id="ghost",
                ),
                request_id="r8", created_by=99,
            )
        mock_dept_repo.assign_user.assert_not_called()
