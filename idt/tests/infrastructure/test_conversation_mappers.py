"""Tests for conversation entity-model mappers.

TDD: These tests are written first before implementation.
"""
from datetime import datetime

import pytest

from src.domain.conversation.entities import (
    ConversationMessage,
    ConversationSummary,
    MessageId,
    SummaryId,
)
from src.domain.conversation.value_objects import (
    AgentId,
    MessageRole,
    SessionId,
    TurnIndex,
    UserId,
)
from src.infrastructure.persistence.mappers.conversation_mapper import (
    ConversationMessageMapper,
    ConversationSummaryMapper,
)
from src.infrastructure.persistence.models.conversation import (
    ConversationMessageModel,
    ConversationSummaryModel,
)


class TestConversationMessageMapper:
    """Tests for ConversationMessageMapper."""

    def test_to_entity_converts_model_to_domain_entity(self) -> None:
        """Should convert ORM model to domain entity."""
        now = datetime.now()
        model = ConversationMessageModel(
            id=1,
            user_id="user-123",
            session_id="session-abc",
            agent_id="super",
            role="user",
            content="Hello",
            turn_index=1,
            created_at=now,
        )

        entity = ConversationMessageMapper.to_entity(model)

        assert entity.id is not None
        assert entity.id.value == 1
        assert entity.user_id.value == "user-123"
        assert entity.session_id.value == "session-abc"
        assert entity.role == MessageRole.USER
        assert entity.content == "Hello"
        assert entity.turn_index.value == 1
        assert entity.created_at == now

    def test_to_entity_with_assistant_role(self) -> None:
        """Should handle assistant role correctly."""
        model = ConversationMessageModel(
            id=2,
            user_id="user-123",
            session_id="session-abc",
            agent_id="super",
            role="assistant",
            content="Hi there!",
            turn_index=2,
            created_at=datetime.now(),
        )

        entity = ConversationMessageMapper.to_entity(model)

        assert entity.role == MessageRole.ASSISTANT

    def test_to_model_converts_entity_to_orm_model(self) -> None:
        """Should convert domain entity to ORM model."""
        now = datetime.now()
        entity = ConversationMessage(
            id=MessageId(1),
            user_id=UserId("user-123"),
            session_id=SessionId("session-abc"),
            agent_id=AgentId.super(),
            role=MessageRole.USER,
            content="Hello",
            turn_index=TurnIndex(1),
            created_at=now,
        )

        model = ConversationMessageMapper.to_model(entity)

        assert model.id == 1
        assert model.user_id == "user-123"
        assert model.session_id == "session-abc"
        assert model.role == "user"
        assert model.content == "Hello"
        assert model.turn_index == 1
        assert model.created_at == now

    def test_to_model_without_id(self) -> None:
        """Should handle entity without ID (new entity)."""
        now = datetime.now()
        entity = ConversationMessage(
            id=None,
            user_id=UserId("user-123"),
            session_id=SessionId("session-abc"),
            agent_id=AgentId.super(),
            role=MessageRole.ASSISTANT,
            content="Response",
            turn_index=TurnIndex(2),
            created_at=now,
        )

        model = ConversationMessageMapper.to_model(entity)

        assert model.id is None
        assert model.role == "assistant"


class TestConversationMessageMapperCharts:
    """charts 매핑 테스트 (chat-chart-persistence)."""

    def test_to_entity_maps_charts(self) -> None:
        """JSON 컬럼 list → 엔티티 charts."""
        charts = [{"type": "bar"}, {"type": "line"}, {"type": "pie"}]
        model = ConversationMessageModel(
            id=1,
            user_id="user-123",
            session_id="session-abc",
            agent_id="super",
            role="assistant",
            content="차트 답변",
            turn_index=2,
            charts=charts,
            created_at=datetime.now(),
        )

        entity = ConversationMessageMapper.to_entity(model)

        assert entity.charts == charts

    def test_to_entity_charts_null_maps_to_none(self) -> None:
        model = ConversationMessageModel(
            id=1,
            user_id="user-123",
            session_id="session-abc",
            agent_id="super",
            role="user",
            content="질문",
            turn_index=1,
            charts=None,
            created_at=datetime.now(),
        )

        entity = ConversationMessageMapper.to_entity(model)

        assert entity.charts is None

    def test_to_model_maps_charts(self) -> None:
        """엔티티 charts → JSON 컬럼 list (round-trip)."""
        charts = [{"type": "bar", "data": {"labels": ["a"]}}]
        entity = ConversationMessage(
            id=None,
            user_id=UserId("user-123"),
            session_id=SessionId("session-abc"),
            agent_id=AgentId.super(),
            role=MessageRole.ASSISTANT,
            content="차트 답변",
            turn_index=TurnIndex(2),
            created_at=datetime.now(),
            charts=charts,
        )

        model = ConversationMessageMapper.to_model(entity)

        assert model.charts == charts

    def test_to_model_charts_default_none(self) -> None:
        entity = ConversationMessage(
            id=None,
            user_id=UserId("user-123"),
            session_id=SessionId("session-abc"),
            agent_id=AgentId.super(),
            role=MessageRole.USER,
            content="질문",
            turn_index=TurnIndex(1),
            created_at=datetime.now(),
        )

        model = ConversationMessageMapper.to_model(entity)

        assert model.charts is None


class TestConversationSummaryMapper:
    """Tests for ConversationSummaryMapper."""

    def test_to_entity_converts_model_to_domain_entity(self) -> None:
        """Should convert ORM model to domain entity."""
        now = datetime.now()
        model = ConversationSummaryModel(
            id=1,
            user_id="user-123",
            session_id="session-abc",
            agent_id="super",
            summary_content="User discussed settings.",
            start_turn=1,
            end_turn=4,
            created_at=now,
        )

        entity = ConversationSummaryMapper.to_entity(model)

        assert entity.id is not None
        assert entity.id.value == 1
        assert entity.user_id.value == "user-123"
        assert entity.session_id.value == "session-abc"
        assert entity.summary_content == "User discussed settings."
        assert entity.start_turn.value == 1
        assert entity.end_turn.value == 4
        assert entity.created_at == now

    def test_to_model_converts_entity_to_orm_model(self) -> None:
        """Should convert domain entity to ORM model."""
        now = datetime.now()
        entity = ConversationSummary(
            id=SummaryId(1),
            user_id=UserId("user-123"),
            session_id=SessionId("session-abc"),
            agent_id=AgentId.super(),
            summary_content="User asked about features.",
            start_turn=TurnIndex(1),
            end_turn=TurnIndex(3),
            created_at=now,
        )

        model = ConversationSummaryMapper.to_model(entity)

        assert model.id == 1
        assert model.user_id == "user-123"
        assert model.session_id == "session-abc"
        assert model.summary_content == "User asked about features."
        assert model.start_turn == 1
        assert model.end_turn == 3
        assert model.created_at == now

    def test_to_model_without_id(self) -> None:
        """Should handle entity without ID (new entity)."""
        now = datetime.now()
        entity = ConversationSummary(
            id=None,
            user_id=UserId("user-123"),
            session_id=SessionId("session-abc"),
            agent_id=AgentId.super(),
            summary_content="Summary content.",
            start_turn=TurnIndex(1),
            end_turn=TurnIndex(5),
            created_at=now,
        )

        model = ConversationSummaryMapper.to_model(entity)

        assert model.id is None
