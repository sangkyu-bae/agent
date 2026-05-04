"""대화 히스토리 조회 도메인 스키마 (CHAT-HIST-001)."""
from dataclasses import dataclass
from datetime import datetime
from typing import List

LAST_MESSAGE_MAX_LENGTH = 100


@dataclass(frozen=True)
class SessionSummary:
    """세션 요약 정보."""

    session_id: str
    message_count: int
    last_message: str
    last_message_at: datetime

    @classmethod
    def from_raw(
        cls,
        session_id: str,
        message_count: int,
        last_message: str,
        last_message_at: datetime,
    ) -> "SessionSummary":
        """last_message를 100자로 truncate하여 SessionSummary 생성."""
        truncated = (last_message or "")[:LAST_MESSAGE_MAX_LENGTH]
        return cls(
            session_id=session_id,
            message_count=message_count,
            last_message=truncated,
            last_message_at=last_message_at,
        )


@dataclass(frozen=True)
class SessionListResponse:
    """사용자 세션 목록 응답."""

    user_id: str
    sessions: List[SessionSummary]


@dataclass(frozen=True)
class MessageItem:
    """세션 내 단일 메시지 항목."""

    id: int
    role: str
    content: str
    turn_index: int
    created_at: datetime


@dataclass(frozen=True)
class MessageListResponse:
    """세션 메시지 전체 목록 응답."""

    user_id: str
    session_id: str
    messages: List[MessageItem]


@dataclass(frozen=True)
class AgentChatSummary:
    """대화 기록이 있는 에이전트 요약."""

    agent_id: str
    agent_name: str
    session_count: int
    last_chat_at: datetime


@dataclass(frozen=True)
class AgentListResponse:
    """사용자의 에이전트 목록 응답."""

    user_id: str
    agents: List[AgentChatSummary]


@dataclass(frozen=True)
class AgentSessionListResponse:
    """에이전트별 세션 목록 응답."""

    user_id: str
    agent_id: str
    sessions: List[SessionSummary]


@dataclass(frozen=True)
class AgentMessageListResponse:
    """에이전트별 세션 메시지 응답."""

    user_id: str
    agent_id: str
    session_id: str
    messages: List[MessageItem]
