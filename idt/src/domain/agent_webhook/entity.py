"""agent-webhook 도메인 엔티티: AgentWebhook (V057).

시각 규격: 모든 datetime 은 UTC naive (agent_schedule 선례).
secret 은 평문 보관 엔티티지만 응답·로그에는 hint 만 노출한다 (Design D2).
"""
from dataclasses import dataclass
from datetime import datetime


@dataclass
class AgentWebhook:
    id: str
    agent_id: str
    enabled: bool
    secret: str
    secret_hint: str
    outbound_url: str | None
    outbound_enabled: bool
    created_by: str
    created_at: datetime
    updated_at: datetime


@dataclass
class WebhookDelivery:
    """outbound 발송 이력 (V058) — 불변 레코드 (INSERT only, D20)."""

    id: str
    agent_id: str
    run_id: str | None
    url: str
    trigger_source: str  # "schedule" | "webhook"
    success: bool
    status_code: int | None
    attempts: int
    error: str | None
    duration_ms: int
    created_at: datetime
