from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection.permission_policy import CollectionPermissionPolicy
from src.domain.collection.permission_schemas import (
    CollectionPermission,
    CollectionScope,
)
from src.domain.department.entity import UserDepartment
from src.application.collection.permission_service import (
    CollectionPermissionService,
)
from datetime import datetime


def _user(user_id: int = 1, role: UserRole = UserRole.USER) -> User:
    return User(
        email="test@test.com",
        password_hash="hash",
        role=role,
        status=UserStatus.APPROVED,
        id=user_id,
    )


def _perm(
    collection_name: str = "test-col",
    owner_id: int = 1,
    scope: CollectionScope = CollectionScope.PERSONAL,
    department_id: str | None = None,
) -> CollectionPermission:
    return CollectionPermission(
        collection_name=collection_name,
        owner_id=owner_id,
        scope=scope,
        department_id=department_id,
    )


@pytest.fixture
def mock_perm_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_dept_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.find_departments_by_user.return_value = []
    return repo


@pytest.fixture
def mock_logger() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(
    mock_perm_repo: AsyncMock,
    mock_dept_repo: AsyncMock,
    mock_logger: MagicMock,
) -> CollectionPermissionService:
    return CollectionPermissionService(
        perm_repo=mock_perm_repo,
        dept_repo=mock_dept_repo,
        policy=CollectionPermissionPolicy(),
        logger=mock_logger,
    )


class TestGetUserDeptIds:
    async def test_returns_dept_ids(
        self, service: CollectionPermissionService, mock_dept_repo: AsyncMock
    ) -> None:
        mock_dept_repo.find_departments_by_user.return_value = [
            UserDepartment(user_id=1, department_id="d1", is_primary=True, created_at=datetime.now()),
            UserDepartment(user_id=1, department_id="d2", is_primary=False, created_at=datetime.now()),
        ]
        result = await service.get_user_dept_ids(_user(user_id=1), "req-1")
        assert result == ["d1", "d2"]

    async def test_returns_empty_when_no_id(
        self, service: CollectionPermissionService
    ) -> None:
        user = User(email="a@b.com", password_hash="h", id=None)
        result = await service.get_user_dept_ids(user, "req-1")
        assert result == []


class TestCheckReadAccess:
    async def test_allows_when_no_permission_record(
        self, service: CollectionPermissionService, mock_perm_repo: AsyncMock
    ) -> None:
        mock_perm_repo.find_by_collection_name.return_value = None
        await service.check_read_access("legacy-col", _user(), "req-1")

    async def test_allows_owner_personal(
        self, service: CollectionPermissionService, mock_perm_repo: AsyncMock
    ) -> None:
        mock_perm_repo.find_by_collection_name.return_value = _perm(owner_id=1)
        await service.check_read_access("test-col", _user(user_id=1), "req-1")

    async def test_denies_non_owner_personal(
        self, service: CollectionPermissionService, mock_perm_repo: AsyncMock
    ) -> None:
        mock_perm_repo.find_by_collection_name.return_value = _perm(owner_id=1)
        with pytest.raises(PermissionError, match="No read access"):
            await service.check_read_access("test-col", _user(user_id=2), "req-1")

    async def test_admin_always_allowed(
        self, service: CollectionPermissionService, mock_perm_repo: AsyncMock
    ) -> None:
        mock_perm_repo.find_by_collection_name.return_value = _perm(owner_id=1)
        admin = _user(user_id=99, role=UserRole.ADMIN)
        await service.check_read_access("test-col", admin, "req-1")


class TestCheckWriteAccess:
    async def test_allows_owner_personal(
        self, service: CollectionPermissionService, mock_perm_repo: AsyncMock
    ) -> None:
        mock_perm_repo.find_by_collection_name.return_value = _perm(owner_id=1)
        await service.check_write_access("test-col", _user(user_id=1), "req-1")

    async def test_denies_non_owner_public(
        self, service: CollectionPermissionService, mock_perm_repo: AsyncMock
    ) -> None:
        mock_perm_repo.find_by_collection_name.return_value = _perm(
            owner_id=1, scope=CollectionScope.PUBLIC
        )
        with pytest.raises(PermissionError, match="No write access"):
            await service.check_write_access("test-col", _user(user_id=2), "req-1")


class TestCheckDeleteAccess:
    async def test_owner_can_delete(
        self, service: CollectionPermissionService, mock_perm_repo: AsyncMock
    ) -> None:
        mock_perm_repo.find_by_collection_name.return_value = _perm(owner_id=1)
        await service.check_delete_access("test-col", _user(user_id=1), "req-1")

    async def test_non_owner_cannot_delete(
        self, service: CollectionPermissionService, mock_perm_repo: AsyncMock
    ) -> None:
        mock_perm_repo.find_by_collection_name.return_value = _perm(owner_id=1)
        with pytest.raises(PermissionError, match="No delete access"):
            await service.check_delete_access("test-col", _user(user_id=2), "req-1")


class TestGetAccessibleCollectionNames:
    async def test_admin_returns_empty_set(
        self, service: CollectionPermissionService
    ) -> None:
        admin = _user(user_id=99, role=UserRole.ADMIN)
        result = await service.get_accessible_collection_names(admin, "req-1")
        assert result == set()

    async def test_user_returns_accessible_names(
        self,
        service: CollectionPermissionService,
        mock_perm_repo: AsyncMock,
    ) -> None:
        mock_perm_repo.find_accessible.return_value = [
            _perm(collection_name="col-a"),
            _perm(collection_name="col-b"),
        ]
        result = await service.get_accessible_collection_names(
            _user(user_id=1), "req-1"
        )
        assert result == {"col-a", "col-b"}


class TestChangeScope:
    async def test_raises_when_perm_not_found(
        self, service: CollectionPermissionService, mock_perm_repo: AsyncMock
    ) -> None:
        mock_perm_repo.find_by_collection_name.return_value = None
        with pytest.raises(ValueError, match="Permission not found"):
            await service.change_scope(
                "unknown", _user(), CollectionScope.PUBLIC, None, "req-1"
            )

    async def test_raises_when_no_permission(
        self, service: CollectionPermissionService, mock_perm_repo: AsyncMock
    ) -> None:
        mock_perm_repo.find_by_collection_name.return_value = _perm(owner_id=1)
        with pytest.raises(PermissionError, match="No permission to change"):
            await service.change_scope(
                "test-col", _user(user_id=2), CollectionScope.PUBLIC, None, "req-1"
            )

    async def test_success(
        self, service: CollectionPermissionService, mock_perm_repo: AsyncMock
    ) -> None:
        mock_perm_repo.find_by_collection_name.return_value = _perm(owner_id=1)
        await service.change_scope(
            "test-col", _user(user_id=1), CollectionScope.PUBLIC, None, "req-1"
        )
        mock_perm_repo.update_scope.assert_awaited_once()


class TestOnCollectionDeleted:
    async def test_calls_delete(
        self, service: CollectionPermissionService, mock_perm_repo: AsyncMock
    ) -> None:
        await service.on_collection_deleted("test-col", "req-1")
        mock_perm_repo.delete_by_collection_name.assert_awaited_once_with(
            "test-col", "req-1"
        )


class TestOnCollectionRenamed:
    async def test_calls_update_name(
        self, service: CollectionPermissionService, mock_perm_repo: AsyncMock
    ) -> None:
        await service.on_collection_renamed("old", "new", "req-1")
        mock_perm_repo.update_collection_name.assert_awaited_once_with(
            "old", "new", "req-1"
        )
