"""Multi-Turn Conversation 요청/응답 Value Object."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ConversationChatRequest:
    """대화 질의 요청."""

    user_id: str
    session_id: str
    message: str


@dataclass(frozen=True)
class ConversationChatResponse:
    """대화 응답.

    Attributes:
        was_summarized: 이번 요청에서 오래된 히스토리 요약이 발생했는지 여부
    """

    user_id: str
    session_id: str
    answer: str
    was_summarized: bool
    request_id: str
