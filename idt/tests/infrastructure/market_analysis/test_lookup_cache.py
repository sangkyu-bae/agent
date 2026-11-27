"""TtlLookupCache — 회차 안에서 같은 조회(MCP 서버 등록·실행자)를 DB 에 한 번만 보낸다.

2026-11-27 98번 회차: 근거 수집이 시작되자 서버 조회 15건이 한꺼번에 나가
4건만 바로 끝나고 나머지는 5~8초 뒤에 끝났다 (DB 연결 풀 대기로 추정).
호출마다 서버 등록·사용자 신원을 다시 읽을 이유가 없다.
"""

from __future__ import annotations

import asyncio

import pytest
from src.infrastructure.market_analysis.adapters.lookup_cache import (
    CachedUserReader,
    TtlLookupCache,
)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class CountingLoader:
    def __init__(self, value=object(), fail: Exception | None = None):
        self.calls: list[str] = []
        self.value = value
        self.fail = fail
        self.gate: asyncio.Event | None = None

    async def __call__(self, key: str):
        self.calls.append(key)
        if self.gate is not None:
            await self.gate.wait()
        if self.fail is not None:
            raise self.fail
        return self.value


async def test_second_lookup_within_ttl_hits_the_cache():
    loader, clock = CountingLoader(), Clock()
    cache = TtlLookupCache(loader, ttl_seconds=60, clock=clock)
    first = await cache.get("kis")
    clock.now = 59
    assert await cache.get("kis") is first
    assert loader.calls == ["kis"]


async def test_expired_entry_is_reloaded():
    loader, clock = CountingLoader(), Clock()
    cache = TtlLookupCache(loader, ttl_seconds=60, clock=clock)
    await cache.get("kis")
    clock.now = 61
    await cache.get("kis")
    assert loader.calls == ["kis", "kis"]


async def test_concurrent_misses_share_one_load():
    loader = CountingLoader()
    loader.gate = asyncio.Event()
    cache = TtlLookupCache(loader, ttl_seconds=60, clock=Clock())
    tasks = [asyncio.ensure_future(cache.get("kis")) for _ in range(15)]
    for _ in range(5):
        await asyncio.sleep(0)
    loader.gate.set()
    results = await asyncio.gather(*tasks)
    assert loader.calls == ["kis"]
    assert all(r is results[0] for r in results)


async def test_keys_are_separate():
    loader = CountingLoader()
    cache = TtlLookupCache(loader, ttl_seconds=60, clock=Clock())
    await cache.get("kis")
    await cache.get("dart")
    assert loader.calls == ["kis", "dart"]


async def test_failure_is_not_cached():
    loader = CountingLoader(fail=ConnectionError("db down"))
    cache = TtlLookupCache(loader, ttl_seconds=60, clock=Clock())
    with pytest.raises(ConnectionError):
        await cache.get("kis")
    loader.fail = None
    await cache.get("kis")
    assert loader.calls == ["kis", "kis"]


async def test_none_is_not_cached():
    """없는 서버·사용자는 곧 등록될 수 있다 — 기억하지 않는다."""
    loader = CountingLoader(value=None)
    cache = TtlLookupCache(loader, ttl_seconds=60, clock=Clock())
    assert await cache.get("kis") is None
    assert await cache.get("kis") is None
    assert loader.calls == ["kis", "kis"]


async def test_concurrent_waiters_all_see_the_failure():
    loader = CountingLoader(fail=ConnectionError("db down"))
    loader.gate = asyncio.Event()
    cache = TtlLookupCache(loader, ttl_seconds=60, clock=Clock())
    tasks = [asyncio.ensure_future(cache.get("kis")) for _ in range(3)]
    for _ in range(5):
        await asyncio.sleep(0)
    loader.gate.set()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    assert all(isinstance(r, ConnectionError) for r in results)
    assert loader.calls == ["kis"]


async def test_cached_user_reader_reads_each_user_once():
    class Reader:
        def __init__(self):
            self.calls: list[int] = []

        async def find_by_id(self, user_id: int):
            self.calls.append(user_id)
            return {"id": user_id}

    inner = Reader()
    reader = CachedUserReader(inner, ttl_seconds=60, clock=Clock())
    assert await reader.find_by_id(7) == {"id": 7}
    await reader.find_by_id(7)
    await reader.find_by_id(8)
    assert inner.calls == [7, 8]


async def test_cached_server_finder_keys_by_server_id_only():
    calls: list[tuple[str, str]] = []

    async def finder(server_id, request_id):
        calls.append((server_id, request_id))
        return {"id": server_id}

    from src.infrastructure.market_analysis.adapters.lookup_cache import (
        CachedServerFinder,
    )

    find = CachedServerFinder(finder, ttl_seconds=60, clock=Clock())
    await find("kis", "r1")
    await find("kis", "r2")  # 요청 ID 가 달라도 같은 서버면 다시 읽지 않는다
    assert calls == [("kis", "r1")]
