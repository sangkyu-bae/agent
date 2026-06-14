"""In-memory ChatStreamCache — TTL + LRU 단일 인스턴스 구현.

Design ws-chat-streaming §3.3 / Plan Q3 replay 초기 구현체.

멀티 인스턴스 확장이 필요해지면 같은 `ChatStreamCacheInterface`를
구현하는 RedisChatStreamCache로 swap만 하면 된다.
"""
import asyncio
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

from src.domain.general_chat.interfaces import ChatStreamCacheInterface
from src.domain.general_chat.value_objects import ChatEvent


class InMemoryChatStreamCache(ChatStreamCacheInterface):
    """TTL 기반 in-memory cache.

    - per-session TTL (기본 5분), 접근 시점에 만료 항목 evict.
    - 전체 session 수가 `max_sessions` 초과 시 가장 오래된 항목 LRU evict.
    - record 시 lastUpdated를 갱신해 활성 session을 보존.
    """

    def __init__(self, ttl_seconds: int = 300, max_sessions: int = 1000) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._max = max_sessions
        # session_id -> (last_updated_utc, events)
        self._store: OrderedDict[str, tuple[datetime, list[ChatEvent]]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def record(self, session_id: str, event: ChatEvent) -> None:
        async with self._lock:
            self._evict_expired()
            now = datetime.now(timezone.utc)
            if session_id in self._store:
                _, events = self._store.pop(session_id)
                events.append(event)
                self._store[session_id] = (now, events)
            else:
                if len(self._store) >= self._max:
                    self._store.popitem(last=False)  # LRU
                self._store[session_id] = (now, [event])

    async def replay(self, session_id: str) -> list[ChatEvent]:
        async with self._lock:
            self._evict_expired()
            pair = self._store.get(session_id)
            return list(pair[1]) if pair else []

    async def clear(self, session_id: str) -> None:
        async with self._lock:
            self._store.pop(session_id, None)

    def _evict_expired(self) -> None:
        now = datetime.now(timezone.utc)
        expired = [
            sid for sid, (ts, _) in self._store.items() if now - ts > self._ttl
        ]
        for sid in expired:
            del self._store[sid]
