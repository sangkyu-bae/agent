"""WebSocket domain interfaces — ConnectionManager ABC."""
from abc import ABC, abstractmethod
from typing import Any, Optional

from fastapi import WebSocket


class ConnectionManagerInterface(ABC):
    @abstractmethod
    async def connect(
        self, websocket: WebSocket, user_id: int, room_id: Optional[str] = None
    ) -> None: ...

    @abstractmethod
    async def disconnect(
        self, websocket: WebSocket, user_id: int, room_id: Optional[str] = None
    ) -> None: ...

    @abstractmethod
    async def send_personal(
        self, websocket: WebSocket, message: dict[str, Any]
    ) -> None: ...

    @abstractmethod
    async def send_to_room(
        self, room_id: str, message: dict[str, Any]
    ) -> None: ...

    @abstractmethod
    async def broadcast(
        self, message: dict[str, Any]
    ) -> None: ...

    @abstractmethod
    def get_connection_count(self) -> int: ...

    @abstractmethod
    def get_room_count(self, room_id: str) -> int: ...
