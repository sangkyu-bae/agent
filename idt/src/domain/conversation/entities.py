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
    # chat-chart-persistence D6: 표시 전용 차트 메타.
    # D7-rev1(chart-context-continuity): full config는 LLM 컨텍스트 미투입,
    # 캡션 1줄만 투입(ChartCaptionPolicy). 편집 후속 질문 시 변환 경로에서 로드.
    charts: Optional[list[dict]] = None
    # analysis-data-continuity D1: 분석 원천 데이터 스냅샷 (None = 없음).
    # 다음 턴 컨텍스트에 재주입되며 summarizer 입력에는 미포함.
    analysis_data: Optional[dict] = None

    def __post_init__(self) -> None:
        if not self.content or not self.content.strip():
            raise ValueError("Message content cannot be empty")
        # D2: 빈 배열 금지 — 차트가 없으면 None으로 표현
        if self.charts is not None and len(self.charts) == 0:
            raise ValueError("charts must be None when empty")
        if self.analysis_data is not None and not self.analysis_data.get("items"):
            raise ValueError("analysis_data must be None when it has no items")


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
