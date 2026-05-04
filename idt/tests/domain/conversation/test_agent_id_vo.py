"""AgentId VO 테스트 (AGENT-CHAT-001)."""
import pytest

from src.domain.conversation.value_objects import AgentId, SUPER_AGENT_ID


class TestAgentId:

    def test_create_super_agent_id(self) -> None:
        aid = AgentId("super")
        assert aid.value == "super"
        assert aid.is_super is True

    def test_create_custom_agent_id(self) -> None:
        aid = AgentId("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        assert aid.is_super is False

    def test_empty_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="AgentId cannot be empty"):
            AgentId("")

    def test_whitespace_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="AgentId cannot be empty"):
            AgentId("   ")

    def test_super_factory_method(self) -> None:
        aid = AgentId.super()
        assert aid.value == SUPER_AGENT_ID
        assert aid.is_super is True

    def test_equality(self) -> None:
        a1 = AgentId("super")
        a2 = AgentId.super()
        assert a1 == a2
