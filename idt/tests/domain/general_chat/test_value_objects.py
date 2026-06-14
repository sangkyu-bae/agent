"""ChatEventType + ChatEvent VO tests (TDD: written before implementation).

Design ws-chat-streaming §3.1.
"""
from datetime import datetime, timezone

import pytest

from src.domain.general_chat.value_objects import ChatEvent, ChatEventType


class TestChatEventType:
    def test_members(self) -> None:
        # 7-type catalog (ws-chat-streaming §3.1 Q1) +
        # STEP_REASONING (agent-chat-reasoning-display §3.1.2) = 8.
        assert ChatEventType.CHAT_STARTED == "chat_started"
        assert ChatEventType.TOKEN == "chat_token"
        assert ChatEventType.STEP_REASONING == "chat_step_reasoning"
        assert ChatEventType.TOOL_STARTED == "chat_tool_started"
        assert ChatEventType.TOOL_COMPLETED == "chat_tool_completed"
        assert ChatEventType.ANSWER_COMPLETED == "chat_answer_completed"
        assert ChatEventType.CHAT_DONE == "chat_done"
        assert ChatEventType.CHAT_FAILED == "chat_failed"

    def test_member_count(self) -> None:
        assert len(list(ChatEventType)) == 8


class TestChatEvent:
    def _make(self, **overrides):
        kwargs = dict(
            seq=1,
            event_type=ChatEventType.CHAT_STARTED,
            session_id="s-1",
            payload={"k": "v"},
            timestamp=datetime(2026, 5, 25, tzinfo=timezone.utc),
        )
        kwargs.update(overrides)
        return ChatEvent(**kwargs)

    def test_create_with_payload(self) -> None:
        ev = self._make()
        assert ev.seq == 1
        assert ev.event_type == ChatEventType.CHAT_STARTED
        assert ev.session_id == "s-1"
        assert ev.payload["k"] == "v"

    def test_seq_negative_rejected(self) -> None:
        with pytest.raises(ValueError):
            self._make(seq=-1)

    def test_naive_timestamp_rejected(self) -> None:
        with pytest.raises(ValueError):
            self._make(timestamp=datetime(2026, 5, 25))

    def test_frozen(self) -> None:
        ev = self._make()
        with pytest.raises(Exception):
            ev.seq = 99  # type: ignore[misc]

    def test_session_id_optional(self) -> None:
        ev = self._make(session_id=None)
        assert ev.session_id is None
