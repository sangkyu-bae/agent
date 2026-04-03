"""SQLAlchemy ORM models for conversation management.

These models map to the conversation_message and conversation_summary tables.
"""
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class ConversationMessageModel(Base):
    """ORM model for conversation_message table.

    Stores individual messages in a conversation session.
    """

    __tablename__ = "conversation_message"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_message_user_session", "user_id", "session_id"),
    )


class ConversationSummaryModel(Base):
    """ORM model for conversation_summary table.

    Stores summaries of conversation turns for a session.
    """

    __tablename__ = "conversation_summary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    summary_content: Mapped[str] = mapped_column(Text, nullable=False)
    start_turn: Mapped[int] = mapped_column(Integer, nullable=False)
    end_turn: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_summary_user_session", "user_id", "session_id"),
    )
