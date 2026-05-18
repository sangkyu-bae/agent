"""Tests for WebSocket domain schemas (TDD: written before implementation)."""
from datetime import datetime

import pytest

from src.domain.websocket.schemas import (
    WSCloseCode,
    WSConnection,
    WSErrorData,
    WSErrorMessage,
    WSMessage,
    WSMessageType,
)


class TestWSMessageType:
    def test_system_message_types(self) -> None:
        assert WSMessageType.PING == "ping"
        assert WSMessageType.PONG == "pong"
        assert WSMessageType.ERROR == "error"
        assert WSMessageType.CONNECTED == "connected"

    def test_feature_message_types(self) -> None:
        assert WSMessageType.AGENT_STEP == "agent_step"
        assert WSMessageType.CHAT_TOKEN == "chat_token"
        assert WSMessageType.INGEST_PROGRESS == "ingest_progress"


class TestWSMessage:
    def test_create_with_defaults(self) -> None:
        msg = WSMessage(type="connected", data={"user_id": 1})
        assert msg.type == "connected"
        assert msg.data == {"user_id": 1}
        assert isinstance(msg.timestamp, datetime)
        assert msg.metadata is None

    def test_serialize_to_json(self) -> None:
        msg = WSMessage(type="echo", data={"text": "hello"})
        dumped = msg.model_dump(mode="json")
        assert dumped["type"] == "echo"
        assert dumped["data"] == {"text": "hello"}
        assert "timestamp" in dumped

    def test_with_metadata(self) -> None:
        msg = WSMessage(
            type="chat_token",
            data={"token": "hi"},
            metadata={"room_id": "room-1", "seq": 42},
        )
        assert msg.metadata["room_id"] == "room-1"
        assert msg.metadata["seq"] == 42


class TestWSErrorMessage:
    def test_type_fixed_to_error(self) -> None:
        err = WSErrorMessage(data=WSErrorData(code="AUTH_FAILED", message="bad token"))
        assert err.type == "error"

    def test_error_data_fields(self) -> None:
        err = WSErrorMessage(
            data=WSErrorData(code="INTERNAL_ERROR", message="unexpected"),
        )
        assert err.data.code == "INTERNAL_ERROR"
        assert err.data.message == "unexpected"

    def test_serialize_to_json(self) -> None:
        err = WSErrorMessage(data=WSErrorData(code="RATE_LIMITED", message="too many"))
        dumped = err.model_dump(mode="json")
        assert dumped["type"] == "error"
        assert dumped["data"]["code"] == "RATE_LIMITED"


class TestWSConnection:
    def test_create_without_room(self) -> None:
        conn = WSConnection(user_id=1)
        assert conn.user_id == 1
        assert conn.room_id is None
        assert isinstance(conn.connected_at, datetime)

    def test_create_with_room(self) -> None:
        conn = WSConnection(user_id=5, room_id="agent-run-123")
        assert conn.room_id == "agent-run-123"

    def test_frozen(self) -> None:
        conn = WSConnection(user_id=1)
        with pytest.raises(AttributeError):
            conn.user_id = 2  # type: ignore[misc]


class TestWSCloseCode:
    def test_standard_codes(self) -> None:
        assert WSCloseCode.NORMAL == 1000
        assert WSCloseCode.AUTH_FAILED == 4001
        assert WSCloseCode.FORBIDDEN == 4002
        assert WSCloseCode.NOT_FOUND == 4003
        assert WSCloseCode.RATE_LIMITED == 4004
        assert WSCloseCode.INTERNAL_ERROR == 4500
