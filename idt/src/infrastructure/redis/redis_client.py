"""Redis connection pool management."""
import redis.asyncio as redis

from src.infrastructure.config.redis_config import RedisConfig


class RedisClient:
    """Redis 연결 풀 관리 어댑터."""

    def __init__(self, pool: redis.ConnectionPool) -> None:
        self._pool = pool

    @classmethod
    def from_config(cls, config: RedisConfig) -> "RedisClient":
        """설정으로부터 RedisClient 생성."""
        pool = redis.ConnectionPool.from_url(
            config.url,
            max_connections=config.REDIS_MAX_CONNECTIONS,
            decode_responses=False,
        )
        return cls(pool=pool)

    def get_connection(self) -> redis.Redis:
        """연결 풀에서 Redis 연결 반환."""
        return redis.Redis(connection_pool=self._pool)

    async def close(self) -> None:
        """연결 풀 해제."""
        await self._pool.disconnect()
