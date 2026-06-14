"""General Chat domain interfaces (ABC).

ws-chat-streaming Design §3.2.
"""
from abc import ABC, abstractmethod

from src.domain.general_chat.value_objects import ChatEvent


class ChatStreamCacheInterface(ABC):
    """진행 중 + 최근 종료된 chat stream events 캐시.

    Plan Q3 / Design §3.2.
    초기 구현체: `InMemoryChatStreamCache` (TTL 5분).
    멀티 인스턴스 확장 시 Redis 구현체로 swap (interface는 그대로).
    """

    @abstractmethod
    async def record(self, session_id: str, event: ChatEvent) -> None: ...

    @abstractmethod
    async def replay(self, session_id: str) -> list[ChatEvent]: ...

    @abstractmethod
    async def clear(self, session_id: str) -> None:
        """CHAT_DONE/CHAT_FAILED 직후 명시적 삭제 (TTL 백업)."""
        ...
