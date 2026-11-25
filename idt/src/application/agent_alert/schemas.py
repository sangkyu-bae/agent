"""agent_alert 요청/응답 스키마 — firewall-agent design §4.1."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from src.domain.agent_alert.entity import AlertReceipt, AlertReceiver
from src.domain.agent_alert.policies import INSTRUCTION_PREFIX_MAX


def _utc_iso(dt: datetime) -> str:
    """UTC naive 저장값에 오프셋을 붙인다 — 브라우저 로컬 오해석 방지.

    approval-gate G12 선례.
    """
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).isoformat()


def build_inbound_path(agent_id: str) -> str:
    return f"/api/v1/alert-hooks/agents/{agent_id}"


class UpsertAlertReceiverRequest(BaseModel):
    """None 은 '그대로 둠'. 최초 생성 시 기본값: 꺼짐·바쁘면 건너뜀·앞머리 없음."""

    enabled: bool | None = None
    skip_when_busy: bool | None = None
    instruction_prefix: str | None = Field(None, max_length=INSTRUCTION_PREFIX_MAX)


class AlertReceiverConfigResponse(BaseModel):
    configured: bool
    enabled: bool | None = None
    skip_when_busy: bool | None = None
    instruction_prefix: str | None = None
    token_hint: str | None = None
    inbound_path: str | None = None
    updated_at: str | None = None

    @classmethod
    def of(cls, receiver: AlertReceiver | None) -> "AlertReceiverConfigResponse":
        if receiver is None:
            return cls(configured=False)
        return cls(
            configured=True,
            enabled=receiver.enabled,
            skip_when_busy=receiver.skip_when_busy,
            instruction_prefix=receiver.instruction_prefix,
            token_hint=receiver.token_hint,
            inbound_path=build_inbound_path(receiver.agent_id),
            updated_at=_utc_iso(receiver.updated_at),
        )


class UpsertAlertReceiverResponse(BaseModel):
    config: AlertReceiverConfigResponse
    # 최초 생성·재발급 응답에서만 평문 1회. 그 외 None.
    token: str | None = None


class AlertReceiptResponse(BaseModel):
    id: str
    result: str
    skip_reason: str | None
    firing_count: int
    job_id: str | None
    received_at: str

    @classmethod
    def of(cls, receipt: AlertReceipt) -> "AlertReceiptResponse":
        return cls(
            id=receipt.id,
            result=receipt.result,
            skip_reason=receipt.skip_reason,
            firing_count=receipt.firing_count,
            job_id=receipt.job_id,
            received_at=_utc_iso(receipt.received_at),
        )


class ReceiveAlertResponse(BaseModel):
    result: str
    receipt_id: str
    job_id: str | None = None
