"""Tests for RedisRepository CRUD operations."""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_redis():
    """Mock redis.asyncio.Redis instance."""
    r = MagicMock()
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock(return_value=True)
    r.delete = AsyncMock(return_value=1)
    r.exists = AsyncMock(return_value=0)
    r.expire = AsyncMock(return_value=True)
    return r


@pytest.fixture
def mock_client(mock_redis):
    """Mock RedisClient that returns mock_redis."""
    client = MagicMock()
    client.get_connection.return_value = mock_redis
    return client


@pytest.fixture
def repo(mock_client):
    """RedisRepository instance with mocked client."""
    from src.infrastructure.redis.redis_repository import RedisRepository
    return RedisRepository(client=mock_client)


class TestRedisRepositoryGet:
    """get() 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_get_returns_none_when_key_not_found(self, repo, mock_redis):
        mock_redis.get.return_value = None
        result = await repo.get("missing-key")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_returns_decoded_string(self, repo, mock_redis):
        mock_redis.get.return_value = b"hello"
        result = await repo.get("my-key")
        assert result == "hello"

    @pytest.mark.asyncio
    async def test_get_calls_redis_with_correct_key(self, repo, mock_redis):
        await repo.get("test-key")
        mock_redis.get.assert_called_once_with("test-key")


class TestRedisRepositorySet:
    """set() 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_set_stores_value(self, repo, mock_redis):
        await repo.set("key", "value")
        mock_redis.set.assert_called_once_with("key", "value", ex=None)

    @pytest.mark.asyncio
    async def test_set_with_ttl_passes_ex_parameter(self, repo, mock_redis):
        await repo.set("key", "value", ttl=60)
        mock_redis.set.assert_called_once_with("key", "value", ex=60)

    @pytest.mark.asyncio
    async def test_set_without_ttl_passes_none(self, repo, mock_redis):
        await repo.set("key", "value")
        mock_redis.set.assert_called_once_with("key", "value", ex=None)


class TestRedisRepositoryDelete:
    """delete() 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_delete_calls_redis_delete(self, repo, mock_redis):
        await repo.delete("key-to-delete")
        mock_redis.delete.assert_called_once_with("key-to-delete")


class TestRedisRepositoryExists:
    """exists() 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_exists_returns_true_when_key_present(self, repo, mock_redis):
        mock_redis.exists.return_value = 1
        result = await repo.exists("existing-key")
        assert result is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_when_key_absent(self, repo, mock_redis):
        mock_redis.exists.return_value = 0
        result = await repo.exists("missing-key")
        assert result is False


class TestRedisRepositoryExpire:
    """expire() 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_expire_sets_ttl_on_key(self, repo, mock_redis):
        await repo.expire("my-key", ttl=300)
        mock_redis.expire.assert_called_once_with("my-key", 300)
