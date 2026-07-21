"""Eval Router: 답변 평가 + 에이전트 만족도 집계 (agent-eval-gate Design §3-4).

피드백 3종은 인증 사용자 본인 것만(401 / 타·미존재 404 은닉 / 422).
집계 2종은 require_role("admin"). DI는 main.py에서 override.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException

from src.application.eval.api_schemas import (
    AgentEvalStatResponse,
    MyFeedbackResponse,
    RecentNegativeItemResponse,
    SubmitFeedbackRequest,
    to_recent_negative_response,
    to_stat_response,
)
from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import get_current_user, require_role

router = APIRouter(prefix="/api/v1", tags=["Eval"])


# ── DI 플레이스홀더 ─────────────────────────────────────────────

def get_submit_feedback_use_case():
    raise NotImplementedError


def get_get_feedback_use_case():
    raise NotImplementedError


def get_delete_feedback_use_case():
    raise NotImplementedError


def get_agent_eval_stats_use_case():
    raise NotImplementedError


def _raise_feedback_error(exc: ValueError) -> None:
    msg = str(exc)
    raise HTTPException(status_code=404 if "찾을 수 없" in msg else 422, detail=msg)


# ── 피드백 (본인) ───────────────────────────────────────────────

@router.post("/conversations/messages/{message_id}/feedback", response_model=MyFeedbackResponse)
async def submit_feedback(
    message_id: int,
    body: SubmitFeedbackRequest,
    use_case=Depends(get_submit_feedback_use_case),
    user: User = Depends(get_current_user),
):
    """답변 평가 제출/토글 — 같은 rating 재요청 시 취소(rating=None 반환)."""
    request_id = str(uuid.uuid4())
    try:
        saved = await use_case.execute(
            str(user.id), message_id, body.rating, body.comment, request_id
        )
    except ValueError as e:
        _raise_feedback_error(e)
    if saved is None:  # 취소됨
        return MyFeedbackResponse(message_id=message_id, rating=None)
    return MyFeedbackResponse(
        message_id=message_id, rating=saved.rating.value, comment=saved.comment
    )


@router.get("/conversations/messages/{message_id}/feedback", response_model=MyFeedbackResponse)
async def get_feedback(
    message_id: int,
    use_case=Depends(get_get_feedback_use_case),
    user: User = Depends(get_current_user),
):
    """본인 평가 조회 — 없으면 rating=None."""
    request_id = str(uuid.uuid4())
    fb = await use_case.execute(str(user.id), message_id, request_id)
    if fb is None:
        return MyFeedbackResponse(message_id=message_id, rating=None)
    return MyFeedbackResponse(
        message_id=message_id, rating=fb.rating.value, comment=fb.comment
    )


@router.delete("/conversations/messages/{message_id}/feedback", status_code=204)
async def delete_feedback(
    message_id: int,
    use_case=Depends(get_delete_feedback_use_case),
    user: User = Depends(get_current_user),
):
    """본인 평가 취소."""
    request_id = str(uuid.uuid4())
    await use_case.execute(str(user.id), message_id, request_id)


# ── 집계 (admin) ────────────────────────────────────────────────

@router.get("/admin/eval/agents", response_model=list[AgentEvalStatResponse])
async def agent_eval_stats(
    use_case=Depends(get_agent_eval_stats_use_case),
    _admin: User = Depends(require_role("admin")),
):
    """에이전트별 만족도(up/(up+down))·평가 수."""
    request_id = str(uuid.uuid4())
    stats = await use_case.agents(request_id)
    return [to_stat_response(s) for s in stats]


@router.get("/admin/eval/recent-negative", response_model=list[RecentNegativeItemResponse])
async def recent_negative(
    use_case=Depends(get_agent_eval_stats_use_case),
    _admin: User = Depends(require_role("admin")),
):
    """최근 부정 피드백."""
    request_id = str(uuid.uuid4())
    items = await use_case.recent_negative(request_id)
    return [to_recent_negative_response(i) for i in items]
