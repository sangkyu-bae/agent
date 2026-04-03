"""Tests for RedisClient connection management."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestRedisClient:
    """RedisClient 연결 관리 테스트."""

    @patch("src.infrastructure.redis.redis_client.redis.ConnectionPool.from_url")
    def test_create_client_builds_connection_pool(self, mock_pool):
        """from_config() 호출 시 연결 풀이 생성된다."""
        from src.infrastructure.redis.redis_client import RedisClient
        from src.infrastructure.config.redis_config import RedisConfig

        config = RedisConfig(REDIS_HOST="localhost", REDIS_PORT=6379, REDIS_DB=0)
        RedisClient.from_config(config)

        mock_pool.assert_called_once()

    @patch("src.infrastructure.redis.redis_client.redis.ConnectionPool.from_url")
    def test_connection_url_contains_host_and_port(self, mock_pool):
        """연결 URL에 host와 port가 포함된다."""
        from src.infrastructure.redis.redis_client import RedisClient
        from src.infrastructure.config.redis_config import RedisConfig

        config = RedisConfig(REDIS_HOST="myredis", REDIS_PORT=6380, REDIS_DB=1)
        RedisClient.from_config(config)

        call_args = mock_pool.call_args[0][0]
        assert "myredis" in call_args
        assert "6380" in call_args

    @pytest.mark.asyncio
    @patch("src.infrastructure.redis.redis_client.redis.ConnectionPool.from_url")
    async def test_close_disconnects_pool(self, mock_pool):
        """close() 호출 시 연결 풀이 해제된다."""
        from src.infrastructure.redis.redis_client import RedisClient
        from src.infrastructure.config.redis_config import RedisConfig

        pool_instance = MagicMock()
        pool_instance.disconnect = AsyncMock()
        mock_pool.return_value = pool_instance

        config = RedisConfig(REDIS_HOST="localhost", REDIS_PORT=6379, REDIS_DB=0)
        client = RedisClient.from_config(config)
        await client.close()

        pool_instance.disconnect.assert_called_once()
