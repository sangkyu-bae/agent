from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.collection.activity_log_service import ActivityLogService
from src.application.collection.use_case import CollectionManagementUseCase
from src.domain.collection.policy import CollectionPolicy
from src.domain.collection.schemas import (
    CollectionDetail,
    CollectionInfo,
    CreateCollectionRequest,
    DistanceMetric,
)


@pytest.fixture
def mock_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_activity_log() -> AsyncMock:
    return AsyncMock(spec=ActivityLogService)


@pytest.fixture
def use_case(
    mock_repo: AsyncMock, mock_activity_log: AsyncMock
) -> CollectionManagementUseCase:
    return CollectionManagementUseCase(
        repository=mock_repo,
        policy=CollectionPolicy(),
        activity_log=mock_activity_log,
        default_collection="documents",
    )


class TestListCollections:
    async def test_returns_list_and_logs(
        self,
        use_case: CollectionManagementUseCase,
        mock_repo: AsyncMock,
        mock_activity_log: AsyncMock,
    ) -> None:
        info = CollectionInfo("docs", 10, 10, "green")
        mock_repo.list_collections.return_value = [info]

        result = await use_case.list_collections("req-1", "user1")
        assert result == [info]
        mock_activity_log.log.assert_awaited_once()


class TestGetCollection:
    async def test_success(
        self, use_case: CollectionManagementUseCase, mock_repo: AsyncMock
    ) -> None:
        detail = CollectionDetail("test", 5, 5, "green", 1536, "Cosine")
        mock_repo.get_collection.return_value = detail
        result = await use_case.get_collection("test", "req-1")
        assert result == detail

    async def test_not_found_raises(
        self, use_case: CollectionManagementUseCase, mock_repo: AsyncMock
    ) -> None:
        mock_repo.get_collection.return_value = None
        with pytest.raises(ValueError, match="not found"):
            await use_case.get_collection("nonexistent", "req-1")


class TestCreateCollection:
    async def test_success(
        self, use_case: CollectionManagementUseCase, mock_repo: AsyncMock
    ) -> None:
        mock_repo.collection_exists.return_value = False
        req = CreateCollectionRequest("new-col", 1536, DistanceMetric.COSINE)
        await use_case.create_collection(req, "req-1", "user1")
        mock_repo.create_collection.assert_awaited_once_with(req)

    async def test_duplicate_raises(
        self, use_case: CollectionManagementUseCase, mock_repo: AsyncMock
    ) -> None:
        mock_repo.collection_exists.return_value = True
        req = CreateCollectionRequest("existing", 1536)
        with pytest.raises(ValueError, match="already exists"):
            await use_case.create_collection(req, "req-1")

    async def test_invalid_name_raises(
        self, use_case: CollectionManagementUseCase
    ) -> None:
        req = CreateCollectionRequest("bad name!", 1536)
        with pytest.raises(ValueError, match="Invalid collection name"):
            await use_case.create_collection(req, "req-1")


class TestDeleteCollection:
    async def test_success(
        self, use_case: CollectionManagementUseCase, mock_repo: AsyncMock
    ) -> None:
        mock_repo.collection_exists.return_value = True
        await use_case.delete_collection("my-col", "req-1")
        mock_repo.delete_collection.assert_awaited_once_with("my-col")

    async def test_protected_raises(
        self, use_case: CollectionManagementUseCase
    ) -> None:
        with pytest.raises(ValueError, match="Cannot delete protected"):
            await use_case.delete_collection("documents", "req-1")

    async def test_not_found_raises(
        self, use_case: CollectionManagementUseCase, mock_repo: AsyncMock
    ) -> None:
        mock_repo.collection_exists.return_value = False
        with pytest.raises(ValueError, match="not found"):
            await use_case.delete_collection("ghost", "req-1")


class TestRenameCollection:
    async def test_success(
        self, use_case: CollectionManagementUseCase, mock_repo: AsyncMock
    ) -> None:
        mock_repo.collection_exists.return_value = True
        await use_case.rename_collection("old", "new-name", "req-1")
        mock_repo.update_collection_alias.assert_awaited_once_with("old", "new-name")

    async def test_not_found_raises(
        self, use_case: CollectionManagementUseCase, mock_repo: AsyncMock
    ) -> None:
        mock_repo.collection_exists.return_value = False
        with pytest.raises(ValueError, match="not found"):
            await use_case.rename_collection("ghost", "new-name", "req-1")

    async def test_invalid_new_name_raises(
        self, use_case: CollectionManagementUseCase
    ) -> None:
        with pytest.raises(ValueError, match="Invalid collection name"):
            await use_case.rename_collection("old", "bad name!", "req-1")
