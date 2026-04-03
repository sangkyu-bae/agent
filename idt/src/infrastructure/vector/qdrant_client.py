"""Qdrant client configuration and factory.

Provides configuration and factory methods for creating Qdrant clients.
"""
from dataclasses import dataclass
from typing import Optional

from qdrant_client import AsyncQdrantClient, models


@dataclass
class QdrantClientConfig:
    """Configuration for Qdrant client connection.

    Attributes:
        host: Qdrant server host (default: localhost)
        port: Qdrant server port (default: 6333)
        api_key: Optional API key for authentication
        https: Whether to use HTTPS (default: False)
    """

    host: str = "localhost"
    port: int = 6333
    api_key: Optional[str] = None
    https: bool = False

    @property
    def url(self) -> str:
        """Build the full URL for the Qdrant server."""
        protocol = "https" if self.https else "http"
        return f"{protocol}://{self.host}:{self.port}"


class QdrantClientFactory:
    """Factory for creating Qdrant clients."""

    @staticmethod
    def create(config: Optional[QdrantClientConfig] = None) -> AsyncQdrantClient:
        """Create an async Qdrant client.

        Args:
            config: Optional configuration. Uses defaults if not provided.

        Returns:
            An AsyncQdrantClient instance
        """
        if config is None:
            config = QdrantClientConfig()

        return AsyncQdrantClient(
            host=config.host,
            port=config.port,
            api_key=config.api_key,
            https=config.https,
        )

    @staticmethod
    async def ensure_collection(
        client: AsyncQdrantClient,
        collection_name: str,
        vector_size: int,
    ) -> None:
        """Ensure a collection exists, creating it if necessary.

        Args:
            client: The Qdrant client
            collection_name: Name of the collection
            vector_size: Dimension of vectors to store
        """
        exists = await client.collection_exists(collection_name)

        if not exists:
            await client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
