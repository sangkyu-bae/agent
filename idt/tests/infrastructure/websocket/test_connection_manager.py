"""Tests for ConnectionManager (TDD: written before implementation)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.websocket.schemas import WSCloseCode
from src.infrastructure.websocket.connection_manager import ConnectionManager


def _make_logger() -> MagicMock:
    logger = MagicMock()
    logger.info = MagicMock()
    logger.warning = MagicMock()
    return logger


def _make_ws() -> AsyncMock:
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


class TestConnect:
    @pytest.mark.asyncio
    async def test_connect_increases_count(self) -> None:
        mgr = ConnectionManager(logger=_make_logger())
        ws = _make_ws()
        await mgr.connect(ws, user_id=1)
        assert mgr.get_connection_count() == 1
        ws.accept.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_with_room(self) -> None:
        mgr = ConnectionManager(logger=_make_logger())
        ws = _make_ws()
        await mgr.connect(ws, user_id=1, room_id="room-a")
        assert mgr.get_room_count("room-a") == 1

    @pytest.mark.asyncio
    async def test_max_connections_exceeded(self) -> None:
        mgr = ConnectionManager(logger=_make_logger(), max_connections=1)
        ws1 = _make_ws()
        ws2 = _make_ws()
        await mgr.connect(ws1, user_id=1)
        await mgr.connect(ws2, user_id=2)
        ws2.close.assert_awaited_once()
        assert ws2.close.call_args.kwargs.get("code") == WSCloseCode.RATE_LIMITED
        assert mgr.get_connection_count() == 1


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_decreases_count(self) -> None:
        mgr = ConnectionManager(logger=_make_logger())
        ws = _make_ws()
        await mgr.connect(ws, user_id=1)
        await mgr.disconnect(ws, user_id=1)
        assert mgr.get_connection_count() == 0

    @pytest.mark.asyncio
    async def test_disconnect_removes_from_room(self) -> None:
        mgr = ConnectionManager(logger=_make_logger())
        ws = _make_ws()
        await mgr.connect(ws, user_id=1, room_id="room-a")
        await mgr.disconnect(ws, user_id=1, room_id="room-a")
        assert mgr.get_room_count("room-a") == 0

    @pytest.mark.asyncio
    async def test_disconnect_cleans_empty_room(self) -> None:
        mgr = ConnectionManager(logger=_make_logger())
        ws = _make_ws()
        await mgr.connect(ws, user_id=1, room_id="room-a")
        await mgr.disconnect(ws, user_id=1, room_id="room-a")
        assert "room-a" not in mgr._rooms


class TestSendToRoom:
    @pytest.mark.asyncio
    async def test_send_to_room_only_targets_same_room(self) -> None:
        mgr = ConnectionManager(logger=_make_logger())
        ws_a = _make_ws()
        ws_b = _make_ws()
        await mgr.connect(ws_a, user_id=1, room_id="room-a")
        await mgr.connect(ws_b, user_id=2, room_id="room-b")

        await mgr.send_to_room("room-a", {"type": "test"})
        ws_a.send_json.assert_awaited_once_with({"type": "test"})
        ws_b.send_json.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_send_to_room_cleans_dead_connection(self) -> None:
        mgr = ConnectionManager(logger=_make_logger())
        ws = _make_ws()
        ws.send_json.side_effect = RuntimeError("connection lost")
        await mgr.connect(ws, user_id=1, room_id="room-a")

        await mgr.send_to_room("room-a", {"type": "test"})
        assert mgr.get_connection_count() == 0
        assert mgr.get_room_count("room-a") == 0


class TestBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_reaches_all(self) -> None:
        mgr = ConnectionManager(logger=_make_logger())
        ws1 = _make_ws()
        ws2 = _make_ws()
        await mgr.connect(ws1, user_id=1)
        await mgr.connect(ws2, user_id=2)

        await mgr.broadcast({"type": "ping"})
        ws1.send_json.assert_awaited_once_with({"type": "ping"})
        ws2.send_json.assert_awaited_once_with({"type": "ping"})

    @pytest.mark.asyncio
    async def test_broadcast_cleans_dead_connection(self) -> None:
        mgr = ConnectionManager(logger=_make_logger())
        ws_alive = _make_ws()
        ws_dead = _make_ws()
        ws_dead.send_json.side_effect = RuntimeError("gone")
        await mgr.connect(ws_alive, user_id=1)
        await mgr.connect(ws_dead, user_id=2)

        await mgr.broadcast({"type": "ping"})
        assert mgr.get_connection_count() == 1


class TestSendPersonal:
    @pytest.mark.asyncio
    async def test_send_personal(self) -> None:
        mgr = ConnectionManager(logger=_make_logger())
        ws = _make_ws()
        await mgr.send_personal(ws, {"type": "echo", "data": "hi"})
        ws.send_json.assert_awaited_once_with({"type": "echo", "data": "hi"})
