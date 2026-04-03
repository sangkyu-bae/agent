"""Tests for Qdrant client configuration.

Infrastructure tests use mocks as per CLAUDE.md rules.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from src.infrastructure.vector.qdrant_client import (
    QdrantClientConfig,
    QdrantClientFactory,
)


class TestQdrantClientConfig:
    """Tests for QdrantClientConfig."""

    def test_default_config(self) -> None:
        """Default config should use localhost:6333."""
        config = QdrantClientConfig()
        assert config.host == "localhost"
        assert config.port == 6333
        assert config.api_key is None
        assert config.https is False

    def test_custom_config(self) -> None:
        """Should accept custom configuration."""
        config = QdrantClientConfig(
            host="qdrant.example.com",
            port=6334,
            api_key="test-api-key",
            https=True,
        )
        assert config.host == "qdrant.example.com"
        assert config.port == 6334
        assert config.api_key == "test-api-key"
        assert config.https is True

    def test_url_property_http(self) -> None:
        """URL should use http when https is False."""
        config = QdrantClientConfig(host="localhost", port=6333, https=False)
        assert config.url == "http://localhost:6333"

    def test_url_property_https(self) -> None:
        """URL should use https when https is True."""
        config = QdrantClientConfig(host="qdrant.example.com", port=443, https=True)
        assert config.url == "https://qdrant.example.com:443"


class TestQdrantClientFactory:
    """Tests for QdrantClientFactory."""

    def test_create_client_with_default_config(self) -> None:
        """Should create client with default configuration."""
        with patch(
            "src.infrastructure.vector.qdrant_client.AsyncQdrantClient"
        ) as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client

            client = QdrantClientFactory.create()

            mock_cls.assert_called_once_with(
                host="localhost",
                port=6333,
                api_key=None,
                https=False,
            )
            assert client == mock_client

    def test_create_client_with_custom_config(self) -> None:
        """Should create client with custom configuration."""
        config = QdrantClientConfig(
            host="qdrant.example.com",
            port=6334,
            api_key="test-key",
            https=True,
        )

        with patch(
            "src.infrastructure.vector.qdrant_client.AsyncQdrantClient"
        ) as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client

            client = QdrantClientFactory.create(config)

            mock_cls.assert_called_once_with(
                host="qdrant.example.com",
                port=6334,
                api_key="test-key",
                https=True,
            )

    @pytest.mark.asyncio
    async def test_ensure_collection_creates_if_not_exists(self) -> None:
        """Should create collection if it doesn't exist."""
        mock_client = MagicMock()
        mock_client.collection_exists = AsyncMock(return_value=False)
        mock_client.create_collection = AsyncMock()

        with patch(
            "src.infrastructure.vector.qdrant_client.models"
        ) as mock_models:
            mock_models.VectorParams.return_value = MagicMock()
            mock_models.Distance.COSINE = "Cosine"

            await QdrantClientFactory.ensure_collection(
                client=mock_client,
                collection_name="test_collection",
                vector_size=1536,
            )

            mock_client.collection_exists.assert_called_once_with("test_collection")
            mock_client.create_collection.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_collection_skips_if_exists(self) -> None:
        """Should not create collection if it already exists."""
        mock_client = MagicMock()
        mock_client.collection_exists = AsyncMock(return_value=True)
        mock_client.create_collection = AsyncMock()

        await QdrantClientFactory.ensure_collection(
            client=mock_client,
            collection_name="test_collection",
            vector_size=1536,
        )

        mock_client.collection_exists.assert_called_once_with("test_collection")
        mock_client.create_collection.assert_not_called()
