"""InMemoryChatStreamCache tests.

Design ws-chat-streaming §3.3 — Plan Q3 replay 지원 초기 구현체.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from src.domain.general_chat.value_objects import ChatEvent, ChatEventType
from src.infrastructure.general_chat.stream_cache import InMemoryChatStreamCache


def _ev(seq: int, et: ChatEventType = ChatEventType.TOKEN, sid: str = "s1") -> ChatEvent:
    return ChatEvent(
        seq=seq,
        event_type=et,
        session_id=sid,
        payload={"i": seq},
        timestamp=datetime(2026, 5, 25, tzinfo=timezone.utc),
    )


class TestRecordReplay:
    @pytest.mark.asyncio
    async def test_replay_returns_events_in_record_order(self) -> None:
        cache = InMemoryChatStreamCache()
        await cache.record("s1", _ev(1))
        await cache.record("s1", _ev(2))
        await cache.record("s1", _ev(3))
        out = await cache.replay("s1")
        assert [e.seq for e in out] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_replay_unknown_session_returns_empty(self) -> None:
        cache = InMemoryChatStreamCache()
        assert await cache.replay("nonexistent") == []

    @pytest.mark.asyncio
    async def test_clear_removes_session(self) -> None:
        cache = InMemoryChatStreamCache()
        await cache.record("s1", _ev(1))
        await cache.clear("s1")
        assert await cache.replay("s1") == []

    @pytest.mark.asyncio
    async def test_clear_unknown_session_is_noop(self) -> None:
        cache = InMemoryChatStreamCache()
        await cache.clear("nope")  # must not raise

    @pytest.mark.asyncio
    async def test_sessions_isolated(self) -> None:
        cache = InMemoryChatStreamCache()
        await cache.record("a", _ev(1, sid="a"))
        await cache.record("b", _ev(2, sid="b"))
        assert [e.seq for e in await cache.replay("a")] == [1]
        assert [e.seq for e in await cache.replay("b")] == [2]


class TestTTLEviction:
    @pytest.mark.asyncio
    async def test_expired_session_evicted_on_access(self, monkeypatch) -> None:
        cache = InMemoryChatStreamCache(ttl_seconds=1)
        await cache.record("s1", _ev(1))

        # 시간을 강제로 미래로 이동 (datetime.now 패치)
        future = datetime.now(timezone.utc) + timedelta(seconds=5)

        class _FakeDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return future

        monkeypatch.setattr(
            "src.infrastructure.general_chat.stream_cache.datetime",
            _FakeDateTime,
        )
        assert await cache.replay("s1") == []


class TestLRU:
    @pytest.mark.asyncio
    async def test_oldest_evicted_when_max_exceeded(self) -> None:
        cache = InMemoryChatStreamCache(max_sessions=2)
        await cache.record("a", _ev(1, sid="a"))
        await cache.record("b", _ev(2, sid="b"))
        await cache.record("c", _ev(3, sid="c"))  # evicts 'a'
        assert await cache.replay("a") == []
        assert [e.seq for e in await cache.replay("b")] == [2]
        assert [e.seq for e in await cache.replay("c")] == [3]


class TestConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_records_serialized(self) -> None:
        cache = InMemoryChatStreamCache()
        await asyncio.gather(*[cache.record("s", _ev(i)) for i in range(20)])
        out = await cache.replay("s")
        assert len(out) == 20
        # asyncio.gather 순서는 보장 안되지만 모든 record 반영 검증
        assert sorted(e.seq for e in out) == list(range(20))
