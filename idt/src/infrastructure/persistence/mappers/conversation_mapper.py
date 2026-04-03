"""Mappers for converting between domain entities and ORM models.

These mappers handle the conversion between the domain layer's entities
and the infrastructure layer's ORM models.
"""
from typing import Optional

from src.domain.conversation.entities import (
    ConversationMessage,
    ConversationSummary,
    MessageId,
    SummaryId,
)
from src.domain.conversation.value_objects import (
    MessageRole,
    SessionId,
    TurnIndex,
    UserId,
)
from src.infrastructure.persistence.models.conversation import (
    ConversationMessageModel,
    ConversationSummaryModel,
)


class ConversationMessageMapper:
    """Mapper for ConversationMessage entity and model."""

    @staticmethod
    def to_entity(model: ConversationMessageModel) -> ConversationMessage:
        """Convert ORM model to domain entity.

        Args:
            model: The ORM model to convert

        Returns:
            Domain entity representation
        """
        return ConversationMessage(
            id=MessageId(model.id) if model.id else None,
            user_id=UserId(model.user_id),
            session_id=SessionId(model.session_id),
            role=MessageRole.from_string(model.role),
            content=model.content,
            turn_index=TurnIndex(model.turn_index),
            created_at=model.created_at,
        )

    @staticmethod
    def to_model(entity: ConversationMessage) -> ConversationMessageModel:
        """Convert domain entity to ORM model.

        Args:
            entity: The domain entity to convert

        Returns:
            ORM model representation
        """
        return ConversationMessageModel(
            id=entity.id.value if entity.id else None,
            user_id=entity.user_id.value,
            session_id=entity.session_id.value,
            role=entity.role.value,
            content=entity.content,
            turn_index=entity.turn_index.value,
            created_at=entity.created_at,
        )


class ConversationSummaryMapper:
    """Mapper for ConversationSummary entity and model."""

    @staticmethod
    def to_entity(model: ConversationSummaryModel) -> ConversationSummary:
        """Convert ORM model to domain entity.

        Args:
            model: The ORM model to convert

        Returns:
            Domain entity representation
        """
        return ConversationSummary(
            id=SummaryId(model.id) if model.id else None,
            user_id=UserId(model.user_id),
            session_id=SessionId(model.session_id),
            summary_content=model.summary_content,
            start_turn=TurnIndex(model.start_turn),
            end_turn=TurnIndex(model.end_turn),
            created_at=model.created_at,
        )

    @staticmethod
    def to_model(entity: ConversationSummary) -> ConversationSummaryModel:
        """Convert domain entity to ORM model.

        Args:
            entity: The domain entity to convert

        Returns:
            ORM model representation
        """
        return ConversationSummaryModel(
            id=entity.id.value if entity.id else None,
            user_id=entity.user_id.value,
            session_id=entity.session_id.value,
            summary_content=entity.summary_content,
            start_turn=entity.start_turn.value,
            end_turn=entity.end_turn.value,
            created_at=entity.created_at,
        )
