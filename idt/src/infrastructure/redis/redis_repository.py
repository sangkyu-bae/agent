"""Redis repository implementation."""
from typing import Optional

from src.domain.redis.interfaces import RedisRepositoryInterface
from src.infrastructure.redis.redis_client import RedisClient


class RedisRepository(RedisRepositoryInterface):
    """RedisRepositoryInterface의 redis-py 구현체."""

    def __init__(self, client: RedisClient) -> None:
        self._client = client

    async def get(self, key: str) -> Optional[str]:
        """키에 대한 값 조회. 없으면 None 반환."""
        r = self._client.get_connection()
        value = await r.get(key)
        if value is None:
            return None
        return value.decode("utf-8") if isinstance(value, bytes) else value

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        """키-값 저장. ttl(초) 지정 시 만료 시간 설정."""
        r = self._client.get_connection()
        await r.set(key, value, ex=ttl)

    async def delete(self, key: str) -> None:
        """키 삭제."""
        r = self._client.get_connection()
        await r.delete(key)

    async def exists(self, key: str) -> bool:
        """키 존재 여부 확인."""
        r = self._client.get_connection()
        count = await r.exists(key)
        return count > 0

    async def expire(self, key: str, ttl: int) -> None:
        """기존 키에 TTL 설정."""
        r = self._client.get_connection()
        await r.expire(key, ttl)
