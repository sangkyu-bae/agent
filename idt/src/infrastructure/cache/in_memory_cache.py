"""InMemoryCache: 프로세스 로컬 TTL 캐시 어댑터.

Design Ref: admin-default-llm-routing §4.1 / §8.2.

단일 서버 구간의 기본 구현이다. 다중 서버로 전환하면 동일 포트에 Redis
어댑터를 추가하고 이 클래스를 교체한다 — 소비자 코드는 수정하지 않는다.
"""
import copy
import time
from typing import Any, Callable

from src.domain.cache.interfaces import CachePort


class InMemoryCache(CachePort):
    """딕셔너리 기반 TTL 캐시.

    - 만료는 조회 시점에 lazy 삭제한다 (백그라운드 스윕 없음).
    - ``max_entries`` 초과 시 삽입 순서가 가장 오래된 항목을 축출한다
      (``dict`` 는 삽입 순서를 보존한다).
    - ``clock`` 을 주입해 TTL 만료를 결정적으로 테스트한다
      (CostCalculator 선례).
    - 저장·조회 시 깊은 복사를 수행해 값 의미론을 보장한다
      (CachePort 계약 2 — Redis 어댑터와 동일 동작).
    """

    def __init__(
        self,
        *,
        default_ttl_seconds: float | None = None,
        max_entries: int = 1000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._default_ttl = default_ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        # key -> (value, expires_at | None)
        self._store: dict[str, tuple[Any, float | None]] = {}

    async def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None

        value, expires_at = entry
        if expires_at is not None and expires_at <= self._clock():
            self._store.pop(key, None)
            return None

        return copy.deepcopy(value)

    async def set(
        self, key: str, value: Any, ttl_seconds: float | None = None
    ) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        expires_at = None if ttl is None else self._clock() + ttl

        # 덮어쓰기는 신규 삽입이 아니므로 축출 대상이 아니다.
        if key not in self._store:
            self._evict_if_needed()

        self._store[key] = (copy.deepcopy(value), expires_at)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def clear(self) -> None:
        self._store.clear()

    def size(self) -> int:
        """현재 보관 중인 항목 수 (만료됐지만 아직 회수되지 않은 항목 포함)."""
        return len(self._store)

    def _evict_if_needed(self) -> None:
        """상한을 지키도록 가장 오래된 항목부터 축출한다."""
        while self._store and len(self._store) >= self._max_entries:
            oldest_key = next(iter(self._store))
            self._store.pop(oldest_key, None)
