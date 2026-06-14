"""ChatEventWsAdapter tests — ChatEvent → WSMessage.

Design ws-chat-streaming §3.4.
mock 금지 — pure mapper.
"""
from datetime import datetime, timezone

import pytest

from src.domain.general_chat.value_objects import ChatEvent, ChatEventType
from src.domain.websocket.schemas import WSMessage
from src.infrastructure.general_chat.ws_adapter import ChatEventWsAdapter


def _ev(
    seq: int = 1,
    event_type: ChatEventType = ChatEventType.CHAT_STARTED,
    payload: dict | None = None,
) -> ChatEvent:
    return ChatEvent(
        seq=seq,
        event_type=event_type,
        session_id="s-1",
        payload=payload if payload is not None else {"k": "v"},
        timestamp=datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc),
    )


class TestToWsMessage:
    def test_returns_ws_message(self) -> None:
        assert isinstance(ChatEventWsAdapter.to_ws_message(_ev()), WSMessage)

    @pytest.mark.parametrize(
        "event_type, expected",
        [
            (ChatEventType.CHAT_STARTED, "chat_started"),
            (ChatEventType.TOKEN, "chat_token"),
            (ChatEventType.STEP_REASONING, "chat_step_reasoning"),
            (ChatEventType.TOOL_STARTED, "chat_tool_started"),
            (ChatEventType.TOOL_COMPLETED, "chat_tool_completed"),
            (ChatEventType.ANSWER_COMPLETED, "chat_answer_completed"),
            (ChatEventType.CHAT_DONE, "chat_done"),
            (ChatEventType.CHAT_FAILED, "chat_failed"),
        ],
    )
    def test_all_seven_event_types(
        self, event_type: ChatEventType, expected: str
    ) -> None:
        out = ChatEventWsAdapter.to_ws_message(_ev(event_type=event_type))
        assert out.type == expected

    def test_payload_preserved_as_data(self) -> None:
        payload = {"chunk": "안", "node": "x"}
        out = ChatEventWsAdapter.to_ws_message(
            _ev(event_type=ChatEventType.TOKEN, payload=payload)
        )
        assert out.data == payload

    def test_metadata_default(self) -> None:
        out = ChatEventWsAdapter.to_ws_message(_ev(seq=42))
        assert out.metadata is not None
        assert out.metadata["seq"] == 42
        assert out.metadata["ts"].startswith("2026-05-25T12:00:00")
        assert "cached" not in out.metadata  # default: not cached

    def test_metadata_cached_flag(self) -> None:
        # Replay 시 cached=True를 명시적으로 표시 (FE가 "이어보기" 표시 가능)
        out = ChatEventWsAdapter.to_ws_message(_ev(seq=5), cached=True)
        assert out.metadata["cached"] is True

    def test_korean_payload_preserved(self) -> None:
        out = ChatEventWsAdapter.to_ws_message(
            _ev(event_type=ChatEventType.TOKEN, payload={"chunk": "안녕"})
        )
        dumped = out.model_dump(mode="json")
        assert dumped["data"]["chunk"] == "안녕"

    def test_step_reasoning_payload_pass_through(self) -> None:
        # agent-chat-reasoning-display Design §4.1
        payload = {
            "step_name": "chat_agent",
            "reasoning": "RAG 검색을 사용합니다.",
            "tool_calls": ["rag_search"],
        }
        out = ChatEventWsAdapter.to_ws_message(
            _ev(event_type=ChatEventType.STEP_REASONING, payload=payload)
        )
        assert out.type == "chat_step_reasoning"
        assert out.data == payload
