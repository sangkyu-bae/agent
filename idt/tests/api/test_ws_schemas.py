"""SubscribeAgentRunPayload tests — WS 첫 메시지(subscribe) Pydantic 검증.

Design fe-websocket-integration-guide §4.1.
"""
import pytest
from pydantic import ValidationError

from src.api.routes.ws_schemas import SubscribeAgentRunPayload, SubscribeChatPayload


class TestSubscribeAgentRunPayload:
    def test_minimal_valid(self) -> None:
        payload = SubscribeAgentRunPayload.model_validate(
            {"type": "subscribe", "agent_id": "agent-1", "query": "hello"}
        )
        assert payload.type == "subscribe"
        assert payload.agent_id == "agent-1"
        assert payload.query == "hello"
        assert payload.session_id is None

    def test_with_session_id(self) -> None:
        payload = SubscribeAgentRunPayload.model_validate(
            {
                "type": "subscribe",
                "agent_id": "agent-1",
                "query": "hi",
                "session_id": "sess-99",
            }
        )
        assert payload.session_id == "sess-99"

    def test_wrong_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SubscribeAgentRunPayload.model_validate(
                {"type": "publish", "agent_id": "a", "query": "q"}
            )

    def test_missing_agent_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SubscribeAgentRunPayload.model_validate(
                {"type": "subscribe", "query": "q"}
            )

    def test_missing_query_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SubscribeAgentRunPayload.model_validate(
                {"type": "subscribe", "agent_id": "a"}
            )

    def test_empty_agent_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SubscribeAgentRunPayload.model_validate(
                {"type": "subscribe", "agent_id": "", "query": "q"}
            )

    def test_empty_query_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SubscribeAgentRunPayload.model_validate(
                {"type": "subscribe", "agent_id": "a", "query": ""}
            )


class TestSubscribeChatPayload:
    def test_minimal_valid(self) -> None:
        p = SubscribeChatPayload.model_validate(
            {"type": "subscribe", "message": "hello"}
        )
        assert p.type == "subscribe"
        assert p.message == "hello"
        assert p.top_k == 5  # default
        assert p.llm_model_id is None

    def test_with_top_k_and_model(self) -> None:
        p = SubscribeChatPayload.model_validate(
            {
                "type": "subscribe",
                "message": "hi",
                "top_k": 10,
                "llm_model_id": "gpt-4o",
            }
        )
        assert p.top_k == 10
        assert p.llm_model_id == "gpt-4o"

    def test_wrong_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SubscribeChatPayload.model_validate(
                {"type": "publish", "message": "hi"}
            )

    def test_empty_message_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SubscribeChatPayload.model_validate(
                {"type": "subscribe", "message": ""}
            )

    def test_top_k_bounds(self) -> None:
        with pytest.raises(ValidationError):
            SubscribeChatPayload.model_validate(
                {"type": "subscribe", "message": "x", "top_k": 0}
            )
        with pytest.raises(ValidationError):
            SubscribeChatPayload.model_validate(
                {"type": "subscribe", "message": "x", "top_k": 100}
            )
