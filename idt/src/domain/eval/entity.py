"""MessageFeedback 도메인 엔티티 (agent-eval-gate).

답변(assistant 메시지)에 대한 사용자 평가 한 건. 외부 호출 없이 값·규칙만 보관.
검증은 src.domain.eval.policies.EvalPolicy 가 담당한다.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Rating(str, Enum):
    """답변 평가 — 좋아요/싫어요."""

    UP = "up"
    DOWN = "down"


@dataclass
class MessageFeedback:
    """assistant 메시지 평가 한 건.

    Attributes:
        id: PK (저장 전 None)
        message_id: conversation_message.id (assistant)
        user_id: 평가자 (GeneralChatRequest.user_id 체계)
        agent_id: 메시지의 agent_id 파생 (general-chat sentinel 포함)
        rating: up|down
        comment: 선택 코멘트 (EvalPolicy.COMMENT_MAX 이하)
    """

    id: int | None
    message_id: int
    user_id: str
    agent_id: str
    rating: Rating
    comment: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
