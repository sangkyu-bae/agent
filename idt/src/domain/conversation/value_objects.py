"""Value objects for conversation domain.

These are immutable objects that represent domain concepts with validation.
"""
from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class UserId:
    """Represents a user identifier."""

    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("UserId cannot be empty")


@dataclass(frozen=True)
class SessionId:
    """Represents a conversation session identifier."""

    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("SessionId cannot be empty")


@dataclass(frozen=True)
class TurnIndex:
    """Represents the turn number in a conversation.

    Business rule: TurnIndex must be >= 1 (turn indices start from 1)
    """

    value: int

    def __post_init__(self) -> None:
        if self.value < 1:
            raise ValueError("TurnIndex must be >= 1")


SUPER_AGENT_ID = "super"


@dataclass(frozen=True)
class AgentId:
    """에이전트 식별자. 일반 채팅은 'super', 커스텀 에이전트는 UUID."""

    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("AgentId cannot be empty")

    @classmethod
    def super(cls) -> "AgentId":
        return cls(SUPER_AGENT_ID)

    @property
    def is_super(self) -> bool:
        return self.value == SUPER_AGENT_ID


class MessageRole(Enum):
    """Allowed roles for conversation messages.

    Only "user" and "assistant" are valid roles.
    """

    USER = "user"
    ASSISTANT = "assistant"

    @classmethod
    def from_string(cls, role: str) -> "MessageRole":
        """Create MessageRole from string value.

        Args:
            role: String representation of the role ("user" or "assistant")

        Returns:
            MessageRole enum value

        Raises:
            ValueError: If role is not a valid message role
        """
        for member in cls:
            if member.value == role:
                return member
        raise ValueError(f"Invalid message role: {role}")
