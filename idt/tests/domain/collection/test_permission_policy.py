"""Domain policy tests for collection permissions — mock 금지."""
import pytest

from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection.permission_policy import CollectionPermissionPolicy
from src.domain.collection.permission_schemas import (
    CollectionPermission,
    CollectionScope,
)


def _user(user_id: int = 1, role: UserRole = UserRole.USER) -> User:
    return User(
        email="test@test.com",
        password_hash="hash",
        role=role,
        status=UserStatus.APPROVED,
        id=user_id,
    )


def _perm(
    owner_id: int = 1,
    scope: CollectionScope = CollectionScope.PERSONAL,
    department_id: str | None = None,
) -> CollectionPermission:
    return CollectionPermission(
        collection_name="test-collection",
        owner_id=owner_id,
        scope=scope,
        department_id=department_id,
    )


class TestCanRead:
    def test_admin_can_read_any(self) -> None:
        admin = _user(user_id=99, role=UserRole.ADMIN)
        perm = _perm(owner_id=1, scope=CollectionScope.PERSONAL)
        assert CollectionPermissionPolicy.can_read(admin, perm, []) is True

    def test_owner_can_read_personal(self) -> None:
        user = _user(user_id=1)
        perm = _perm(owner_id=1, scope=CollectionScope.PERSONAL)
        assert CollectionPermissionPolicy.can_read(user, perm, []) is True

    def test_non_owner_cannot_read_personal(self) -> None:
        user = _user(user_id=2)
        perm = _perm(owner_id=1, scope=CollectionScope.PERSONAL)
        assert CollectionPermissionPolicy.can_read(user, perm, []) is False

    def test_dept_member_can_read_department(self) -> None:
        user = _user(user_id=2)
        perm = _perm(owner_id=1, scope=CollectionScope.DEPARTMENT, department_id="d1")
        assert CollectionPermissionPolicy.can_read(user, perm, ["d1"]) is True

    def test_non_dept_member_cannot_read_department(self) -> None:
        user = _user(user_id=2)
        perm = _perm(owner_id=1, scope=CollectionScope.DEPARTMENT, department_id="d1")
        assert CollectionPermissionPolicy.can_read(user, perm, ["d2"]) is False

    def test_anyone_can_read_public(self) -> None:
        user = _user(user_id=99)
        perm = _perm(owner_id=1, scope=CollectionScope.PUBLIC)
        assert CollectionPermissionPolicy.can_read(user, perm, []) is True


class TestCanWrite:
    def test_admin_can_write_any(self) -> None:
        admin = _user(user_id=99, role=UserRole.ADMIN)
        perm = _perm(owner_id=1, scope=CollectionScope.PERSONAL)
        assert CollectionPermissionPolicy.can_write(admin, perm, []) is True

    def test_owner_can_write_personal(self) -> None:
        user = _user(user_id=1)
        perm = _perm(owner_id=1, scope=CollectionScope.PERSONAL)
        assert CollectionPermissionPolicy.can_write(user, perm, []) is True

    def test_non_owner_cannot_write_personal(self) -> None:
        user = _user(user_id=2)
        perm = _perm(owner_id=1, scope=CollectionScope.PERSONAL)
        assert CollectionPermissionPolicy.can_write(user, perm, []) is False

    def test_dept_member_can_write_department(self) -> None:
        user = _user(user_id=2)
        perm = _perm(owner_id=1, scope=CollectionScope.DEPARTMENT, department_id="d1")
        assert CollectionPermissionPolicy.can_write(user, perm, ["d1"]) is True

    def test_non_dept_member_cannot_write_department(self) -> None:
        user = _user(user_id=2)
        perm = _perm(owner_id=1, scope=CollectionScope.DEPARTMENT, department_id="d1")
        assert CollectionPermissionPolicy.can_write(user, perm, ["d2"]) is False

    def test_non_owner_cannot_write_public(self) -> None:
        user = _user(user_id=2)
        perm = _perm(owner_id=1, scope=CollectionScope.PUBLIC)
        assert CollectionPermissionPolicy.can_write(user, perm, []) is False


class TestCanDeleteCollection:
    def test_admin_can_delete(self) -> None:
        admin = _user(user_id=99, role=UserRole.ADMIN)
        perm = _perm(owner_id=1)
        assert CollectionPermissionPolicy.can_delete_collection(admin, perm) is True

    def test_owner_can_delete(self) -> None:
        user = _user(user_id=1)
        perm = _perm(owner_id=1)
        assert CollectionPermissionPolicy.can_delete_collection(user, perm) is True

    def test_non_owner_cannot_delete(self) -> None:
        user = _user(user_id=2)
        perm = _perm(owner_id=1)
        assert CollectionPermissionPolicy.can_delete_collection(user, perm) is False


class TestCanChangeScope:
    def test_admin_can_change(self) -> None:
        admin = _user(user_id=99, role=UserRole.ADMIN)
        perm = _perm(owner_id=1)
        assert CollectionPermissionPolicy.can_change_scope(admin, perm) is True

    def test_owner_can_change(self) -> None:
        user = _user(user_id=1)
        perm = _perm(owner_id=1)
        assert CollectionPermissionPolicy.can_change_scope(user, perm) is True

    def test_non_owner_cannot_change(self) -> None:
        user = _user(user_id=2)
        perm = _perm(owner_id=1)
        assert CollectionPermissionPolicy.can_change_scope(user, perm) is False


class TestValidateScopeChange:
    def test_department_requires_dept_id(self) -> None:
        with pytest.raises(ValueError, match="department_id is required"):
            CollectionPermissionPolicy.validate_scope_change(
                CollectionScope.DEPARTMENT, None, ["d1"]
            )

    def test_department_must_belong(self) -> None:
        with pytest.raises(ValueError, match="don't belong to"):
            CollectionPermissionPolicy.validate_scope_change(
                CollectionScope.DEPARTMENT, "d2", ["d1"]
            )

    def test_department_valid(self) -> None:
        CollectionPermissionPolicy.validate_scope_change(
            CollectionScope.DEPARTMENT, "d1", ["d1"]
        )

    def test_personal_no_validation(self) -> None:
        CollectionPermissionPolicy.validate_scope_change(
            CollectionScope.PERSONAL, None, []
        )

    def test_public_no_validation(self) -> None:
        CollectionPermissionPolicy.validate_scope_change(
            CollectionScope.PUBLIC, None, []
        )
