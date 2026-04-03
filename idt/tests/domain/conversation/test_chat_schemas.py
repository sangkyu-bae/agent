"""ConversationChatRequest, ConversationChatResponse 스키마 단위 테스트."""
import pytest

from src.domain.conversation.schemas import ConversationChatRequest, ConversationChatResponse


class TestConversationChatRequest:
    def test_basic_fields(self):
        req = ConversationChatRequest(
            user_id="u-1", session_id="s-1", message="안녕하세요"
        )
        assert req.user_id == "u-1"
        assert req.session_id == "s-1"
        assert req.message == "안녕하세요"

    def test_frozen(self):
        req = ConversationChatRequest(user_id="u", session_id="s", message="m")
        with pytest.raises((AttributeError, TypeError)):
            req.message = "변경"  # type: ignore[misc]


class TestConversationChatResponse:
    def test_basic_fields(self):
        resp = ConversationChatResponse(
            user_id="u-1",
            session_id="s-1",
            answer="답변입니다.",
            was_summarized=False,
            request_id="req-1",
        )
        assert resp.answer == "답변입니다."
        assert resp.was_summarized is False

    def test_was_summarized_true(self):
        resp = ConversationChatResponse(
            user_id="u", session_id="s", answer="a", was_summarized=True, request_id="r"
        )
        assert resp.was_summarized is True

    def test_frozen(self):
        resp = ConversationChatResponse(
            user_id="u", session_id="s", answer="a", was_summarized=False, request_id="r"
        )
        with pytest.raises((AttributeError, TypeError)):
            resp.answer = "변경"  # type: ignore[misc]
