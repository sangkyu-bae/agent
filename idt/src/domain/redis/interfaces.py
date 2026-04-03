"""Domain interfaces for Redis storage.

Abstract base classes that define contracts for Redis operations.
Implementations live in infrastructure layer.

No external API calls or redis-py usage allowed in domain layer.
"""
from abc import ABC, abstractmethod
from typing import Optional


class RedisRepositoryInterface(ABC):
    """Abstract interface for Redis key-value operations."""

    @abstractmethod
    async def get(self, key: str) -> Optional[str]:
        """Get value by key.

        Args:
            key: Redis key

        Returns:
            Value string if exists, None otherwise
        """

    @abstractmethod
    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        """Set key-value with optional TTL.

        Args:
            key: Redis key
            value: Value to store
            ttl: Time-to-live in seconds (None = no expiry)
        """

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a key.

        Args:
            key: Redis key to delete
        """

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists.

        Args:
            key: Redis key to check

        Returns:
            True if key exists, False otherwise
        """

    @abstractmethod
    async def expire(self, key: str, ttl: int) -> None:
        """Set TTL on an existing key.

        Args:
            key: Redis key
            ttl: Time-to-live in seconds
        """
