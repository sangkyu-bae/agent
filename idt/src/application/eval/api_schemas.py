"""Eval API 스키마 (agent-eval-gate Design §3-4)."""
from pydantic import BaseModel

from src.application.eval.use_cases import AgentEvalStat
from src.domain.eval.entity import MessageFeedback


class SubmitFeedbackRequest(BaseModel):
    rating: str  # up|down
    comment: str | None = None


class FeedbackResponse(BaseModel):
    message_id: int
    rating: str
    comment: str | None = None


class MyFeedbackResponse(BaseModel):
    """본인 평가 조회 — 없으면 rating=None."""

    message_id: int
    rating: str | None = None
    comment: str | None = None


class AgentEvalStatResponse(BaseModel):
    agent_id: str
    up: int
    down: int
    satisfaction: float | None  # 0건이면 None


class RecentNegativeItemResponse(BaseModel):
    message_id: int
    agent_id: str
    comment: str | None = None
    created_at: str | None = None


def to_feedback_response(fb: MessageFeedback) -> FeedbackResponse:
    return FeedbackResponse(
        message_id=fb.message_id, rating=fb.rating.value, comment=fb.comment
    )


def to_stat_response(stat: AgentEvalStat) -> AgentEvalStatResponse:
    return AgentEvalStatResponse(
        agent_id=stat.agent_id, up=stat.up, down=stat.down,
        satisfaction=stat.satisfaction,
    )


def to_recent_negative_response(fb: MessageFeedback) -> RecentNegativeItemResponse:
    return RecentNegativeItemResponse(
        message_id=fb.message_id, agent_id=fb.agent_id, comment=fb.comment,
        created_at=fb.created_at.isoformat() if fb.created_at else None,
    )
