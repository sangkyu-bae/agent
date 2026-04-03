"""Tests for conversation SQLAlchemy ORM models.

TDD: These tests are written first before implementation.
"""
from datetime import datetime

import pytest
from sqlalchemy import inspect

from src.infrastructure.persistence.models.base import Base
from src.infrastructure.persistence.models.conversation import (
    ConversationMessageModel,
    ConversationSummaryModel,
)


class TestConversationMessageModel:
    """Tests for ConversationMessageModel ORM class."""

    def test_model_has_correct_table_name(self) -> None:
        """Table name should be conversation_message."""
        assert ConversationMessageModel.__tablename__ == "conversation_message"

    def test_model_inherits_from_base(self) -> None:
        """Model should inherit from Base."""
        assert issubclass(ConversationMessageModel, Base)

    def test_model_has_required_columns(self) -> None:
        """Model should have all required columns."""
        mapper = inspect(ConversationMessageModel)
        column_names = [col.key for col in mapper.columns]

        required_columns = [
            "id",
            "user_id",
            "session_id",
            "role",
            "content",
            "turn_index",
            "created_at",
        ]
        for col in required_columns:
            assert col in column_names, f"Missing column: {col}"

    def test_model_instantiation(self) -> None:
        """Should be able to create model instance."""
        now = datetime.now()
        model = ConversationMessageModel(
            user_id="user-123",
            session_id="session-abc",
            role="user",
            content="Hello",
            turn_index=1,
            created_at=now,
        )
        assert model.user_id == "user-123"
        assert model.session_id == "session-abc"
        assert model.role == "user"
        assert model.content == "Hello"
        assert model.turn_index == 1
        assert model.created_at == now

    def test_id_is_primary_key(self) -> None:
        """id column should be primary key."""
        mapper = inspect(ConversationMessageModel)
        pk_columns = [col.name for col in mapper.primary_key]
        assert "id" in pk_columns


class TestConversationSummaryModel:
    """Tests for ConversationSummaryModel ORM class."""

    def test_model_has_correct_table_name(self) -> None:
        """Table name should be conversation_summary."""
        assert ConversationSummaryModel.__tablename__ == "conversation_summary"

    def test_model_inherits_from_base(self) -> None:
        """Model should inherit from Base."""
        assert issubclass(ConversationSummaryModel, Base)

    def test_model_has_required_columns(self) -> None:
        """Model should have all required columns."""
        mapper = inspect(ConversationSummaryModel)
        column_names = [col.key for col in mapper.columns]

        required_columns = [
            "id",
            "user_id",
            "session_id",
            "summary_content",
            "start_turn",
            "end_turn",
            "created_at",
        ]
        for col in required_columns:
            assert col in column_names, f"Missing column: {col}"

    def test_model_instantiation(self) -> None:
        """Should be able to create model instance."""
        now = datetime.now()
        model = ConversationSummaryModel(
            user_id="user-123",
            session_id="session-abc",
            summary_content="User asked about settings.",
            start_turn=1,
            end_turn=4,
            created_at=now,
        )
        assert model.user_id == "user-123"
        assert model.session_id == "session-abc"
        assert model.summary_content == "User asked about settings."
        assert model.start_turn == 1
        assert model.end_turn == 4
        assert model.created_at == now

    def test_id_is_primary_key(self) -> None:
        """id column should be primary key."""
        mapper = inspect(ConversationSummaryModel)
        pk_columns = [col.name for col in mapper.primary_key]
        assert "id" in pk_columns


class TestModelIndexes:
    """Tests for model indexes."""

    def test_message_model_has_user_session_index(self) -> None:
        """ConversationMessageModel should have index on user_id + session_id."""
        indexes = ConversationMessageModel.__table__.indexes
        index_columns = set()
        for idx in indexes:
            cols = tuple(col.name for col in idx.columns)
            index_columns.add(cols)
        # Check for composite index on user_id and session_id
        assert any(
            "user_id" in cols and "session_id" in cols for cols in index_columns
        )

    def test_summary_model_has_user_session_index(self) -> None:
        """ConversationSummaryModel should have index on user_id + session_id."""
        indexes = ConversationSummaryModel.__table__.indexes
        index_columns = set()
        for idx in indexes:
            cols = tuple(col.name for col in idx.columns)
            index_columns.add(cols)
        # Check for composite index on user_id and session_id
        assert any(
            "user_id" in cols and "session_id" in cols for cols in index_columns
        )
