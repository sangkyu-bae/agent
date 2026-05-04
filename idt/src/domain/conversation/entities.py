"""Domain entities for conversation management.

These are the core domain objects representing conversation messages and summaries.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from src.domain.conversation.value_objects import (
    AgentId,
    UserId,
    SessionId,
    TurnIndex,
    MessageRole,
)


@dataclass(frozen=True)
class MessageId:
    """Represents a message identifier."""

    value: int

    def __post_init__(self) -> None:
        if self.value < 1:
            raise ValueError("MessageId must be positive")


@dataclass(frozen=True)
class SummaryId:
    """Represents a summary identifier."""

    value: int

    def __post_init__(self) -> None:
        if self.value < 1:
            raise ValueError("SummaryId must be positive")


@dataclass(frozen=True)
class ConversationMessage:
    """Represents a single message in a conversation.

    A message belongs to a specific user and session, and has a turn index
    indicating its position in the conversation.
    """

    id: Optional[MessageId]
    user_id: UserId
    session_id: SessionId
    agent_id: AgentId
    role: MessageRole
    content: str
    turn_index: TurnIndex
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.content or not self.content.strip():
            raise ValueError("Message content cannot be empty")


@dataclass(frozen=True)
class ConversationSummary:
    """Represents a summary of conversation turns.

    Summaries cover a range of turns (start_turn to end_turn inclusive)
    and are used to provide context without including full conversation history.
    """

    id: Optional[SummaryId]
    user_id: UserId
    session_id: SessionId
    agent_id: AgentId
    summary_content: str
    start_turn: TurnIndex
    end_turn: TurnIndex
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.summary_content or not self.summary_content.strip():
            raise ValueError("Summary content cannot be empty")
        if self.end_turn.value < self.start_turn.value:
            raise ValueError("end_turn must be >= start_turn")
