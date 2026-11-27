"""회차 안에서 반복되는 조회(MCP 서버 등록·실행자 신원)를 짧게 기억한다.

2026-11-27 98번 회차: 근거 수집이 시작되자 서버 조회 15건이 한꺼번에 나가
4건만 바로 끝나고 나머지는 5~8초 뒤에 끝났다 (DB 연결 풀 대기로 추정).
MCP 호출마다 서버 등록과 사용자 신원을 다시 읽었기 때문이다.

- TTL 안에서는 DB 에 다시 가지 않는다. 등록·사용자 변경은 TTL 뒤에 반영된다
- 같은 키를 동시에 조회하면 DB 에는 한 번만 간다
- 실패와 None(없음)은 기억하지 않는다 — 곧 고쳐지거나 등록될 수 있다
- 시장 분석 경로에만 쓴다. 채팅·승인 집행 경로의 조회는 그대로다
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Hashable
from typing import Any, Generic, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")

DEFAULT_TTL_SECONDS = 60.0


class TtlLookupCache(Generic[K, V]):
    def __init__(
        self,
        loader: Callable[[K], Awaitable[V | None]],
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._loader = loader
        self._ttl = ttl_seconds
        self._clock = clock
        self._values: dict[K, tuple[float, V]] = {}
        self._inflight: dict[K, asyncio.Future[V | None]] = {}

    async def get(self, key: K) -> V | None:
        hit = self._values.get(key)
        if hit is not None and self._clock() < hit[0]:
            return hit[1]
        pending = self._inflight.get(key)
        if pending is not None:
            return await asyncio.shield(pending)
        future: asyncio.Future[V | None] = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        try:
            value = await self._loader(key)
        except BaseException as e:
            future.set_exception(e)
            future.exception()  # 기다리는 쪽이 없어도 "never retrieved" 경고를 막는다
            raise
        else:
            future.set_result(value)
            if value is not None:
                self._values[key] = (self._clock() + self._ttl, value)
            return value
        finally:
            self._inflight.pop(key, None)


class CachedServerFinder:
    """`(server_id, request_id) -> registration` 조회를 server_id 로 기억한다."""

    def __init__(
        self,
        finder: Callable[[str, str], Awaitable[Any]],
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._finder = finder
        self._request_ids: dict[str, str] = {}
        self._cache: TtlLookupCache[str, Any] = TtlLookupCache(
            self._load, ttl_seconds=ttl_seconds, clock=clock
        )

    async def _load(self, server_id: str) -> Any:
        return await self._finder(server_id, self._request_ids.get(server_id, ""))

    async def __call__(self, server_id: str, request_id: str) -> Any:
        self._request_ids[server_id] = request_id  # 실제 조회 로그에 남길 요청 ID
        return await self._cache.get(server_id)


class CachedUserReader:
    """IdentityHeaderProviderFactory 의 UserReader 를 감싼다."""

    def __init__(
        self,
        reader: Any,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cache: TtlLookupCache[int, Any] = TtlLookupCache(
            reader.find_by_id, ttl_seconds=ttl_seconds, clock=clock
        )

    async def find_by_id(self, user_id: int) -> Any:
        return await self._cache.get(user_id)
