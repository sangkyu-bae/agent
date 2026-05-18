"""WebSocket ConnectionManager implementation."""
from collections import defaultdict
from typing import Any, Optional

from fastapi import WebSocket

from src.domain.logging.interfaces import LoggerInterface
from src.domain.websocket.interfaces import ConnectionManagerInterface
from src.domain.websocket.schemas import WSCloseCode, WSConnection


class ConnectionManager(ConnectionManagerInterface):
    def __init__(self, logger: LoggerInterface, max_connections: int = 100) -> None:
        self._active: dict[WebSocket, WSConnection] = {}
        self._rooms: dict[str, set[WebSocket]] = defaultdict(set)
        self._logger = logger
        self._max_connections = max_connections

    async def connect(
        self, websocket: WebSocket, user_id: int, room_id: Optional[str] = None
    ) -> None:
        if len(self._active) >= self._max_connections:
            await websocket.close(
                code=WSCloseCode.RATE_LIMITED, reason="Max connections reached"
            )
            return
        await websocket.accept()
        self._active[websocket] = WSConnection(user_id=user_id, room_id=room_id)
        if room_id:
            self._rooms[room_id].add(websocket)
        self._logger.info(
            "ws_connected", user_id=user_id, room_id=room_id, total=len(self._active)
        )

    async def disconnect(
        self, websocket: WebSocket, user_id: int, room_id: Optional[str] = None
    ) -> None:
        self._active.pop(websocket, None)
        if room_id and room_id in self._rooms:
            self._rooms[room_id].discard(websocket)
            if not self._rooms[room_id]:
                del self._rooms[room_id]
        self._logger.info(
            "ws_disconnected",
            user_id=user_id,
            room_id=room_id,
            total=len(self._active),
        )

    async def send_personal(
        self, websocket: WebSocket, message: dict[str, Any]
    ) -> None:
        await websocket.send_json(message)

    async def send_to_room(self, room_id: str, message: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in self._rooms.get(room_id, set()):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            conn = self._active.get(ws)
            if conn:
                await self.disconnect(ws, conn.user_id, room_id)

    async def broadcast(self, message: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._active.keys()):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            conn = self._active.get(ws)
            if conn:
                await self.disconnect(ws, conn.user_id, conn.room_id)

    def get_connection_count(self) -> int:
        return len(self._active)

    def get_room_count(self, room_id: str) -> int:
        return len(self._rooms.get(room_id, set()))
