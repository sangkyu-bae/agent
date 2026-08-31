"""InMemoryCache 단위 테스트.

Design Ref: admin-default-llm-routing §8.2 시나리오 C1~C9.
clock 을 주입해 TTL 만료를 결정적으로 검증한다 (CostCalculator 선례).
"""
import pytest

from src.domain.cache.interfaces import CachePort
from src.infrastructure.cache.in_memory_cache import InMemoryCache


class FakeClock:
    """단조 증가 시계 스텁. advance() 로 시간을 전진시킨다."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def cache(clock: FakeClock) -> InMemoryCache:
    return InMemoryCache(default_ttl_seconds=60.0, max_entries=3, clock=clock)


class TestCachePortContract:
    """CachePort 계약 — Design §4.1."""

    def test_in_memory_cache_implements_port(self, cache: InMemoryCache) -> None:
        assert isinstance(cache, CachePort)

    def test_port_cannot_be_instantiated(self) -> None:
        with pytest.raises(TypeError):
            CachePort()  # type: ignore[abstract]


class TestInMemoryCache:
    """C1~C9 — Design §8.2."""

    async def test_c1_set_then_get_returns_value(
        self, cache: InMemoryCache
    ) -> None:
        """C1: set 후 즉시 get 하면 값이 반환된다."""
        await cache.set("llm_model:default", {"id": "m1"})

        assert await cache.get("llm_model:default") == {"id": "m1"}

    async def test_c1_get_missing_key_returns_none(
        self, cache: InMemoryCache
    ) -> None:
        """C1: 없는 키는 None (예외 아님)."""
        assert await cache.get("nope") is None

    async def test_c2_expired_entry_returns_none(
        self, cache: InMemoryCache, clock: FakeClock
    ) -> None:
        """C2: TTL 경과 후 get 하면 None."""
        await cache.set("k", {"v": 1}, ttl_seconds=10.0)
        clock.advance(10.5)

        assert await cache.get("k") is None

    async def test_c2_not_yet_expired_returns_value(
        self, cache: InMemoryCache, clock: FakeClock
    ) -> None:
        """C2: TTL 직전까지는 살아 있다."""
        await cache.set("k", {"v": 1}, ttl_seconds=10.0)
        clock.advance(9.9)

        assert await cache.get("k") == {"v": 1}

    async def test_c3_default_ttl_applied_when_ttl_omitted(
        self, cache: InMemoryCache, clock: FakeClock
    ) -> None:
        """C3: ttl_seconds 생략 시 생성자의 default_ttl_seconds 가 적용된다."""
        await cache.set("k", {"v": 1})

        clock.advance(59.0)
        assert await cache.get("k") == {"v": 1}

        clock.advance(2.0)
        assert await cache.get("k") is None

    async def test_c3_no_expiry_when_both_ttl_none(
        self, clock: FakeClock
    ) -> None:
        """C3: 기본 TTL 도 인자 TTL 도 없으면 만료하지 않는다."""
        cache = InMemoryCache(default_ttl_seconds=None, clock=clock)
        await cache.set("k", {"v": 1})

        clock.advance(10_000.0)

        assert await cache.get("k") == {"v": 1}

    async def test_c4_delete_removes_entry(self, cache: InMemoryCache) -> None:
        """C4: delete 후 get 은 None."""
        await cache.set("k", {"v": 1})
        await cache.delete("k")

        assert await cache.get("k") is None

    async def test_c5_delete_missing_key_does_not_raise(
        self, cache: InMemoryCache
    ) -> None:
        """C5: 없는 키 delete 는 오류가 아니다."""
        await cache.delete("absent")  # 예외가 나면 테스트 실패

        assert await cache.get("absent") is None

    async def test_c6_clear_removes_all(self, cache: InMemoryCache) -> None:
        """C6: clear 후 모든 키가 None."""
        await cache.set("a", {"v": 1})
        await cache.set("b", {"v": 2})

        await cache.clear()

        assert await cache.get("a") is None
        assert await cache.get("b") is None
        assert cache.size() == 0

    async def test_c7_evicts_oldest_when_over_max_entries(
        self, cache: InMemoryCache
    ) -> None:
        """C7: max_entries 초과 시 가장 오래된 항목이 제거되고 크기가 유지된다."""
        await cache.set("k1", {"v": 1})
        await cache.set("k2", {"v": 2})
        await cache.set("k3", {"v": 3})
        await cache.set("k4", {"v": 4})  # max_entries=3 초과

        assert cache.size() == 3
        assert await cache.get("k1") is None
        assert await cache.get("k4") == {"v": 4}

    async def test_c7_overwrite_existing_key_does_not_evict(
        self, cache: InMemoryCache
    ) -> None:
        """C7: 기존 키 덮어쓰기는 신규 삽입이 아니므로 축출이 일어나지 않는다."""
        await cache.set("k1", {"v": 1})
        await cache.set("k2", {"v": 2})
        await cache.set("k3", {"v": 3})

        await cache.set("k1", {"v": 99})

        assert cache.size() == 3
        assert await cache.get("k1") == {"v": 99}
        assert await cache.get("k2") == {"v": 2}

    async def test_c8_expired_entry_is_lazily_removed_on_get(
        self, cache: InMemoryCache, clock: FakeClock
    ) -> None:
        """C8: 만료 항목은 get 시점에 삭제되어 크기가 줄어든다."""
        await cache.set("k", {"v": 1}, ttl_seconds=10.0)
        assert cache.size() == 1

        clock.advance(20.0)
        await cache.get("k")

        assert cache.size() == 0

    async def test_c9_stored_value_is_isolated_from_caller_mutation(
        self, cache: InMemoryCache
    ) -> None:
        """C9: 저장 후 원본을 변경해도 캐시 값은 영향받지 않는다.

        Redis 어댑터는 직렬화 사본을 저장하므로 값 의미론(value semantics)을
        갖는다. 인메모리가 참조를 공유하면 구현 교체 시 동작이 달라진다 (G2).
        """
        original = {"id": "m1", "nested": {"n": 1}}
        await cache.set("k", original)

        original["id"] = "CHANGED"
        original["nested"]["n"] = 999

        cached = await cache.get("k")
        assert cached == {"id": "m1", "nested": {"n": 1}}

    async def test_c9_returned_value_is_isolated_from_cache(
        self, cache: InMemoryCache
    ) -> None:
        """C9: 반환값을 변경해도 캐시에 남은 값은 그대로다."""
        await cache.set("k", {"id": "m1"})

        got = await cache.get("k")
        got["id"] = "CHANGED"

        assert await cache.get("k") == {"id": "m1"}
