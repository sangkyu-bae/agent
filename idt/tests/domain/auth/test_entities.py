"""Domain entity tests for auth — mock 금지."""
import pytest
from src.domain.auth.entities import User, UserRole, UserStatus


class TestUserRole:
    def test_values(self) -> None:
        assert UserRole.USER.value == "user"
        assert UserRole.ADMIN.value == "admin"

    def test_is_str_enum(self) -> None:
        assert isinstance(UserRole.USER, str)


class TestUserStatus:
    def test_values(self) -> None:
        assert UserStatus.PENDING.value == "pending"
        assert UserStatus.APPROVED.value == "approved"
        assert UserStatus.REJECTED.value == "rejected"

    def test_is_str_enum(self) -> None:
        assert isinstance(UserStatus.PENDING, str)


class TestUser:
    def test_default_role_is_user(self) -> None:
        u = User(email="a@b.com", password_hash="hash")
        assert u.role == UserRole.USER

    def test_default_status_is_pending(self) -> None:
        u = User(email="a@b.com", password_hash="hash")
        assert u.status == UserStatus.PENDING

    def test_id_is_none_before_persist(self) -> None:
        u = User(email="a@b.com", password_hash="hash")
        assert u.id is None

    def test_admin_role(self) -> None:
        u = User(email="a@b.com", password_hash="hash", role=UserRole.ADMIN)
        assert u.role == UserRole.ADMIN

    def test_approved_status(self) -> None:
        u = User(email="a@b.com", password_hash="hash", status=UserStatus.APPROVED)
        assert u.status == UserStatus.APPROVED
