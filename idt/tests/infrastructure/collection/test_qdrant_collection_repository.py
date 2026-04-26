from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.collection.schemas import (
    CollectionDetail,
    CollectionInfo,
    CreateCollectionRequest,
    DistanceMetric,
)
from src.infrastructure.collection.qdrant_collection_repository import (
    QdrantCollectionRepository,
)


@pytest.fixture
def mock_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_client: AsyncMock) -> QdrantCollectionRepository:
    return QdrantCollectionRepository(mock_client)


class TestListCollections:
    async def test_returns_collection_infos(
        self, repo: QdrantCollectionRepository, mock_client: AsyncMock
    ) -> None:
        col = MagicMock()
        col.name = "documents"
        mock_client.get_collections.return_value = MagicMock(collections=[col])

        detail = MagicMock()
        detail.indexed_vectors_count = 100
        detail.points_count = 100
        detail.status.value = "green"
        mock_client.get_collection.return_value = detail

        result = await repo.list_collections()
        assert len(result) == 1
        assert result[0] == CollectionInfo(
            name="documents", vectors_count=100, points_count=100, status="green"
        )


class TestGetCollection:
    async def test_returns_none_when_not_exists(
        self, repo: QdrantCollectionRepository, mock_client: AsyncMock
    ) -> None:
        mock_client.collection_exists.return_value = False
        result = await repo.get_collection("nonexistent")
        assert result is None

    async def test_returns_detail(
        self, repo: QdrantCollectionRepository, mock_client: AsyncMock
    ) -> None:
        mock_client.collection_exists.return_value = True
        detail = MagicMock()
        detail.indexed_vectors_count = 50
        detail.points_count = 50
        detail.status.value = "green"
        detail.config.params.vectors.size = 1536
        detail.config.params.vectors.distance.value = "Cosine"
        mock_client.get_collection.return_value = detail

        result = await repo.get_collection("test-col")
        assert result == CollectionDetail(
            name="test-col",
            vectors_count=50,
            points_count=50,
            status="green",
            vector_size=1536,
            distance="Cosine",
        )


class TestCreateCollection:
    async def test_calls_client(
        self, repo: QdrantCollectionRepository, mock_client: AsyncMock
    ) -> None:
        req = CreateCollectionRequest(
            name="new-col", vector_size=1536, distance=DistanceMetric.COSINE
        )
        await repo.create_collection(req)
        mock_client.create_collection.assert_awaited_once()


class TestDeleteCollection:
    async def test_calls_client(
        self, repo: QdrantCollectionRepository, mock_client: AsyncMock
    ) -> None:
        await repo.delete_collection("test-col")
        mock_client.delete_collection.assert_awaited_once_with("test-col")


class TestCollectionExists:
    async def test_delegates_to_client(
        self, repo: QdrantCollectionRepository, mock_client: AsyncMock
    ) -> None:
        mock_client.collection_exists.return_value = True
        assert await repo.collection_exists("test") is True


class TestUpdateCollectionAlias:
    async def test_calls_update_aliases(
        self, repo: QdrantCollectionRepository, mock_client: AsyncMock
    ) -> None:
        await repo.update_collection_alias("old-name", "new-name")
        mock_client.update_collection_aliases.assert_awaited_once()
