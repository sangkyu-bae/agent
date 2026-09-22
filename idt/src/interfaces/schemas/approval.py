"""approval-gate 요청/응답 DTO.

Design Ref: §4. 프론트 타입(`idt_front/src/types/approval.ts`)과 1:1 대응한다.
"""
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_serializer

# 초안 미리보기 길이 — 목록 응답을 가볍게 유지한다. 전문은 상세에서 본다.
DRAFT_PREVIEW_CHARS = 200


def _utc_iso(value: datetime | None) -> str | None:
    """Check G12 — DB 는 UTC naive 를 저장한다. 그대로 직렬화하면 'Z' 가 없어
    프론트 new Date() 가 **로컬 시각**으로 해석해 KST 기준 9시간 어긋난다.
    UTC 임을 명시해 내려준다."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


class _UtcDatetimeModel(BaseModel):
    """모든 datetime 필드를 UTC 표시(+00:00)와 함께 직렬화한다."""

    @field_serializer("*", when_used="json")
    def _serialize_datetimes(self, value):
        return _utc_iso(value) if isinstance(value, datetime) else value


class ApprovalItemResponse(_UtcDatetimeModel):
    """목록 1건. 초안은 미리보기로 잘라 보낸다."""

    id: str
    agent_id: str
    agent_name: str | None = None
    tool_id: str
    draft_preview: str
    status: Literal[
        "pending", "approved", "scheduled",
        "executed", "rejected", "expired", "failed",
    ]
    execute_after: datetime | None = None
    expires_at: datetime
    seen_at: datetime | None = None
    created_at: datetime


class ApprovalListResponse(BaseModel):
    data: list[ApprovalItemResponse]
    pagination: dict


class ApprovalDetailResponse(ApprovalItemResponse):
    """상세 — 초안 전문 + 집행 인자."""

    draft: str
    tool_args: dict
    worker_id: str
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_reason: str | None = None
    executed_at: datetime | None = None
    error_message: str | None = None


class ApprovalDecisionResponse(_UtcDatetimeModel):
    """승인·거절 결과. message 는 화면에 그대로 띄울 수 있는 문구."""

    id: str
    status: str
    execute_after: datetime | None = None
    message: str


class RejectApprovalRequest(BaseModel):
    """거절 사유는 필수다 — 재개 시 에이전트에 주입되므로 빈 값은 무의미."""

    reason: str = Field(..., min_length=1, max_length=1000)


class ApprovalTickResponse(BaseModel):
    """내부 tick 결과 — 관측·모니터링용."""

    claimed_count: int
    executed_count: int
    failed_count: int
    expired_count: int


def to_item(approval, agent_name: str | None = None) -> ApprovalItemResponse:
    return ApprovalItemResponse(
        id=approval.id,
        agent_id=approval.agent_id,
        agent_name=agent_name,
        tool_id=approval.tool_id,
        draft_preview=(approval.draft or "")[:DRAFT_PREVIEW_CHARS],
        status=approval.status,
        execute_after=approval.execute_after,
        expires_at=approval.expires_at,
        seen_at=approval.seen_at,
        created_at=approval.created_at,
    )


def to_detail(approval, agent_name: str | None = None) -> ApprovalDetailResponse:
    return ApprovalDetailResponse(
        **to_item(approval, agent_name).model_dump(),
        draft=approval.draft,
        tool_args=approval.tool_args or {},
        worker_id=approval.worker_id,
        decided_by=approval.decided_by,
        decided_at=approval.decided_at,
        decision_reason=approval.decision_reason,
        executed_at=approval.executed_at,
        error_message=approval.error_message,
    )


class ApprovalGateSettingsResponse(BaseModel):
    """에이전트별 게이트 설정 (approval-gate Check G3)."""

    available: bool  # 카탈로그에서 관리자가 활성화했는가
    enabled: bool  # 이 에이전트에 적용 중인가 (강제 포함)
    is_enforced: bool  # 관리자 강제 — 소유자가 끌 수 없음
    config: dict


class ApprovalGateSettingsRequest(BaseModel):
    """저장할 config. 키 검증은 MiddlewareConfigPolicy 가 한다(미지 키 거부)."""

    mode: str = "always"
    execute_after: str | None = None
    expires_hours: int = 168
    on_expire: str = "expire"
    timezone: str | None = None

    def to_config(self) -> dict:
        data = self.model_dump()
        if data.get("timezone") is None:
            data.pop("timezone")  # 미지정이면 도메인 기본(Asia/Seoul)
        return data
