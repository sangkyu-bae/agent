from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.collection.permission_schemas import (
    CollectionPermission,
    CollectionScope,
)
from src.infrastructure.collection.permission_repository import (
    CollectionPermissionRepository,
)
from src.infrastructure.collection.permission_models import (
    CollectionPermissionModel,
)


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_logger() -> MagicMock:
    return MagicMock()


@pytest.fixture
def repo(
    mock_session: AsyncMock, mock_logger: MagicMock
) -> CollectionPermissionRepository:
    return CollectionPermissionRepository(mock_session, mock_logger)


class TestSave:
    async def test_adds_and_flushes(
        self, repo: CollectionPermissionRepository, mock_session: AsyncMock
    ) -> None:
        perm = CollectionPermission(
            collection_name="my-docs",
            owner_id=1,
            scope=CollectionScope.PERSONAL,
        )
        result = await repo.save(perm, "req-1")
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()
        model = mock_session.add.call_args[0][0]
        assert isinstance(model, CollectionPermissionModel)
        assert model.collection_name == "my-docs"
        assert model.owner_id == 1
        assert model.scope == "PERSONAL"

    async def test_refreshes_model_after_flush(
        self, repo: CollectionPermissionRepository, mock_session: AsyncMock
    ) -> None:
        now = datetime(2026, 4, 26, 9, 0, 0)

        def set_server_defaults(model: CollectionPermissionModel) -> None:
            model.id = 1
            model.created_at = now
            model.updated_at = now

        mock_session.refresh.side_effect = (
            lambda m: set_server_defaults(m)
        )

        perm = CollectionPermission(
            collection_name="test-col",
            owner_id=2,
            scope=CollectionScope.PUBLIC,
        )
        result = await repo.save(perm, "req-2")

        mock_session.refresh.assert_awaited_once()
        assert result.created_at == now
        assert result.updated_at == now


class TestFindByCollectionName:
    async def test_found(
        self, repo: CollectionPermissionRepository, mock_session: AsyncMock
    ) -> None:
        model = CollectionPermissionModel()
        model.id = 1
        model.collection_name = "my-docs"
        model.owner_id = 1
        model.scope = "PERSONAL"
        model.department_id = None
        model.created_at = datetime(2026, 1, 1)
        model.updated_at = datetime(2026, 1, 1)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = model
        mock_session.execute.return_value = mock_result

        result = await repo.find_by_collection_name("my-docs", "req-1")
        assert result is not None
        assert result.collection_name == "my-docs"
        assert result.scope == CollectionScope.PERSONAL

    async def test_not_found(
        self, repo: CollectionPermissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repo.find_by_collection_name("nonexistent", "req-1")
        assert result is None


class TestFindAccessible:
    async def test_returns_public_and_owned(
        self, repo: CollectionPermissionRepository, mock_session: AsyncMock
    ) -> None:
        public_model = CollectionPermissionModel()
        public_model.id = 1
        public_model.collection_name = "public-docs"
        public_model.owner_id = 99
        public_model.scope = "PUBLIC"
        public_model.department_id = None
        public_model.created_at = datetime(2026, 1, 1)
        public_model.updated_at = datetime(2026, 1, 1)

        owned_model = CollectionPermissionModel()
        owned_model.id = 2
        owned_model.collection_name = "my-docs"
        owned_model.owner_id = 1
        owned_model.scope = "PERSONAL"
        owned_model.department_id = None
        owned_model.created_at = datetime(2026, 1, 1)
        owned_model.updated_at = datetime(2026, 1, 1)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [public_model, owned_model]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repo.find_accessible(
            user_id=1, user_dept_ids=[], request_id="req-1"
        )
        assert len(result) == 2
        names = {r.collection_name for r in result}
        assert "public-docs" in names
        assert "my-docs" in names
        mock_session.execute.assert_awaited_once()

    async def test_includes_department_collections(
        self, repo: CollectionPermissionRepository, mock_session: AsyncMock
    ) -> None:
        dept_model = CollectionPermissionModel()
        dept_model.id = 3
        dept_model.collection_name = "team-docs"
        dept_model.owner_id = 10
        dept_model.scope = "DEPARTMENT"
        dept_model.department_id = "dept-1"
        dept_model.created_at = datetime(2026, 1, 1)
        dept_model.updated_at = datetime(2026, 1, 1)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [dept_model]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repo.find_accessible(
            user_id=1, user_dept_ids=["dept-1"], request_id="req-1"
        )
        assert len(result) == 1
        assert result[0].collection_name == "team-docs"
        assert result[0].scope == CollectionScope.DEPARTMENT

    async def test_empty_when_no_matches(
        self, repo: CollectionPermissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repo.find_accessible(
            user_id=999, user_dept_ids=[], request_id="req-1"
        )
        assert result == []


class TestDeleteByCollectionName:
    async def test_executes_and_flushes(
        self, repo: CollectionPermissionRepository, mock_session: AsyncMock
    ) -> None:
        await repo.delete_by_collection_name("my-docs", "req-1")
        mock_session.execute.assert_awaited_once()
        mock_session.flush.assert_awaited_once()


class TestUpdateScope:
    async def test_executes_and_flushes(
        self, repo: CollectionPermissionRepository, mock_session: AsyncMock
    ) -> None:
        await repo.update_scope(
            "my-docs", CollectionScope.DEPARTMENT, "dept-1", "req-1"
        )
        mock_session.execute.assert_awaited_once()
        mock_session.flush.assert_awaited_once()


class TestUpdateCollectionName:
    async def test_executes_and_flushes(
        self, repo: CollectionPermissionRepository, mock_session: AsyncMock
    ) -> None:
        await repo.update_collection_name("old-name", "new-name", "req-1")
        mock_session.execute.assert_awaited_once()
        mock_session.flush.assert_awaited_once()


class TestToDomain:
    def test_converts_model_to_domain(
        self, repo: CollectionPermissionRepository
    ) -> None:
        model = CollectionPermissionModel()
        model.id = 42
        model.collection_name = "team-docs"
        model.owner_id = 5
        model.scope = "DEPARTMENT"
        model.department_id = "dept-001"
        model.created_at = datetime(2026, 4, 1)
        model.updated_at = datetime(2026, 4, 1)

        result = repo._to_domain(model)
        assert isinstance(result, CollectionPermission)
        assert result.id == 42
        assert result.collection_name == "team-docs"
        assert result.scope == CollectionScope.DEPARTMENT
        assert result.department_id == "dept-001"
