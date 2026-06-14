"""General Chat domain value objects.

ws-chat-streaming Design §3.1.

`AgentRunEvent` 와 대칭 구조의 transport-독립 이벤트 카탈로그.
domain 레이어이므로 외부 의존성 0 (dataclass + Enum + typing 만 사용).
"""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class ChatEventType(str, Enum):
    """transport-독립 chat 실행 이벤트 타입 (7개 고정).

    확장 정책 (Plan Q1):
      - 새 도구 추가는 enum 변경 없이 ChatToolStarted/Completed payload의
        `tool_name`으로 구분한다.
      - 진정 새로운 이벤트 클래스(예: GUARDRAIL)가 필요한 경우만 enum 추가.
    """

    CHAT_STARTED = "chat_started"
    TOKEN = "chat_token"
    STEP_REASONING = "chat_step_reasoning"
    TOOL_STARTED = "chat_tool_started"
    TOOL_COMPLETED = "chat_tool_completed"
    ANSWER_COMPLETED = "chat_answer_completed"
    CHAT_DONE = "chat_done"
    CHAT_FAILED = "chat_failed"


@dataclass(frozen=True)
class ChatEvent:
    """transport-독립 chat 실행 이벤트.

    payload는 event_type별로 Design §3.4에 정의된 키만 포함한다.
    session_id는 CHAT_STARTED 직전에는 None일 수 있다 (테스트 호환).
    """

    seq: int
    event_type: ChatEventType
    session_id: Optional[str]
    payload: Mapping[str, Any]
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.seq < 0:
            raise ValueError("seq must be non-negative")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC)")
