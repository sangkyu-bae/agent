"""대화 히스토리 도메인 스키마 테스트 (CHAT-HIST-001)."""
from datetime import datetime

import pytest


class TestSessionSummary:
    def test_create_with_all_fields(self):
        from src.domain.conversation.history_schemas import SessionSummary

        summary = SessionSummary(
            session_id="s-1",
            message_count=4,
            last_message="안녕하세요",
            last_message_at=datetime(2026, 4, 17, 10, 0, 0),
        )

        assert summary.session_id == "s-1"
        assert summary.message_count == 4
        assert summary.last_message == "안녕하세요"
        assert summary.last_message_at == datetime(2026, 4, 17, 10, 0, 0)

    def test_last_message_truncated_when_exceeding_100_chars(self):
        from src.domain.conversation.history_schemas import SessionSummary

        long_text = "a" * 150
        summary = SessionSummary.from_raw(
            session_id="s-1",
            message_count=2,
            last_message=long_text,
            last_message_at=datetime(2026, 4, 17),
        )

        assert len(summary.last_message) == 100
        assert summary.last_message == "a" * 100


class TestSessionListResponse:
    def test_preserves_session_order(self):
        from src.domain.conversation.history_schemas import (
            SessionListResponse,
            SessionSummary,
        )

        s1 = SessionSummary("s-1", 1, "m1", datetime(2026, 4, 17, 10))
        s2 = SessionSummary("s-2", 1, "m2", datetime(2026, 4, 17, 9))
        response = SessionListResponse(user_id="u-1", sessions=[s1, s2])

        assert response.user_id == "u-1"
        assert response.sessions[0].session_id == "s-1"
        assert response.sessions[1].session_id == "s-2"


class TestMessageItem:
    def test_create_with_user_role(self):
        from src.domain.conversation.history_schemas import MessageItem

        item = MessageItem(
            id=1,
            role="user",
            content="안녕",
            turn_index=1,
            created_at=datetime(2026, 4, 17),
        )

        assert item.role == "user"
        assert item.id == 1
        assert item.turn_index == 1
