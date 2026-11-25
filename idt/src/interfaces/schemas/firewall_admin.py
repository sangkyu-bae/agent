"""firewall_admin 요청·응답 스키마.

Design Ref: firewall-admin-console §4.2, §7 — 응답에 토큰 필드를 두지 않는다.
요청은 extra="forbid" 라 actor 를 보내면 422 다(actor 는 서버가 만든다).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr

from src.application.firewall_admin.control_service import FirewallStatus
from src.application.firewall_admin.observability_service import (
    AlertsView,
    AuditView,
    EventsView,
)
from src.domain.firewall_admin.models import (
    AutomationState,
    BlockList,
    BlockResult,
    UnblockResult,
)

AlertStateLiteral = Literal["firing", "pending", "normal", "nodata", "error"]


class BlockRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ip: StrictStr
    ttl_seconds: StrictInt | None = None
    reason: StrictStr


class FwctlStatusResponse(BaseModel):
    configured: bool
    reachable: bool
    dry_run: bool | None = None
    max_ttl_seconds: int | None = None
    ipset_exists: bool | None = None
    version: str | None = None


class GrafanaStatusResponse(BaseModel):
    configured: bool
    dashboard_url: str | None = None


class FirewallStatusResponse(BaseModel):
    enabled: bool = True
    fwctl: FwctlStatusResponse
    grafana: GrafanaStatusResponse
    default_ttl_seconds: int

    @classmethod
    def from_domain(cls, s: FirewallStatus) -> FirewallStatusResponse:
        return cls(
            fwctl=FwctlStatusResponse(
                configured=s.fwctl_configured,
                reachable=s.health.reachable,
                dry_run=s.health.dry_run,
                max_ttl_seconds=s.health.max_ttl_seconds,
                ipset_exists=s.health.ipset_exists,
                version=s.health.version,
            ),
            grafana=GrafanaStatusResponse(
                configured=s.grafana_configured, dashboard_url=s.dashboard_url
            ),
            default_ttl_seconds=s.default_ttl_seconds,
        )


class BlockEntryResponse(BaseModel):
    ip: str
    ttl_remaining_seconds: int
    packets: int
    bytes: int


class BlockListResponse(BaseModel):
    items: list[BlockEntryResponse]
    count: int
    dry_run: bool

    @classmethod
    def from_domain(cls, b: BlockList) -> BlockListResponse:
        return cls(
            items=[
                BlockEntryResponse(
                    ip=e.ip, ttl_remaining_seconds=e.ttl_remaining_seconds,
                    packets=e.packets, bytes=e.bytes,
                )
                for e in b.items
            ],
            count=len(b.items),
            dry_run=b.dry_run,
        )


class BlockResponse(BaseModel):
    ip: str
    ttl_seconds: int
    expires_at: datetime
    reason: str
    dry_run: bool
    request_id: str

    @classmethod
    def from_domain(cls, r: BlockResult) -> BlockResponse:
        return cls(
            ip=r.ip, ttl_seconds=r.ttl_seconds, expires_at=r.expires_at,
            reason=r.reason,
            dry_run=r.dry_run, request_id=r.request_id,
        )


class UnblockResponse(BaseModel):
    ip: str
    removed: bool
    dry_run: bool | None = None
    already_absent: bool
    request_id: str

    @classmethod
    def from_domain(cls, r: UnblockResult, request_id: str) -> UnblockResponse:
        return cls(
            ip=r.ip, removed=r.removed, dry_run=r.dry_run,
            already_absent=r.already_absent, request_id=request_id,
        )


class AlertInstanceResponse(BaseModel):
    src_ip: str | None = None
    state: AlertStateLiteral
    active_at: datetime | None = None
    value: str | None = None


class AlertRuleResponse(BaseModel):
    uid: str
    name: str
    rule_id: str
    kind: str
    severity: str
    action_hint: str
    state: AlertStateLiteral
    description: str
    last_evaluation: datetime | None = None
    instances: list[AlertInstanceResponse]


class AlertsResponse(BaseModel):
    rules: list[AlertRuleResponse]
    firing_count: int
    fetched_at: datetime

    @classmethod
    def from_domain(cls, v: AlertsView) -> AlertsResponse:
        return cls(
            rules=[
                AlertRuleResponse(
                    uid=r.uid, name=r.name, rule_id=r.rule_id, kind=r.kind,
                    severity=r.severity, action_hint=r.action_hint, state=r.state,
                    description=r.description, last_evaluation=r.last_evaluation,
                    instances=[
                        AlertInstanceResponse(
                            src_ip=i.src_ip, state=i.state, active_at=i.active_at,
                            value=i.value,
                        )
                        for i in r.instances
                    ],
                )
                for r in v.rules
            ],
            firing_count=v.firing_count,
            fetched_at=v.fetched_at,
        )


class SourceCountResponse(BaseModel):
    src_ip: str
    count: int


class FirewallEventResponse(BaseModel):
    ts: datetime
    action: str
    src_ip: str | None = None
    dest_ip: str | None = None
    protocol: int | None = None
    dport: int | None = None


class EventsResponse(BaseModel):
    range: str
    action: str
    top_sources: list[SourceCountResponse]
    recent: list[FirewallEventResponse]
    fetched_at: datetime

    @classmethod
    def from_domain(cls, v: EventsView) -> EventsResponse:
        return cls(
            range=v.range, action=v.action,
            top_sources=[SourceCountResponse(src_ip=s.src_ip, count=s.count)
                         for s in v.top_sources],
            recent=[
                FirewallEventResponse(
                    ts=e.ts, action=e.action, src_ip=e.src_ip, dest_ip=e.dest_ip,
                    protocol=e.protocol, dport=e.dport,
                )
                for e in v.recent
            ],
            fetched_at=v.fetched_at,
        )


class AuditRecordResponse(BaseModel):
    ts: datetime
    request_id: str | None = None
    event: str | None = None
    actor: str | None = None
    ip: str | None = None
    ttl_seconds: int | None = None
    reason: str | None = None
    result: str | None = None
    status: int | None = None
    error_code: str | None = None
    dry_run: bool | None = None


class AuditResponse(BaseModel):
    range: str
    items: list[AuditRecordResponse]
    count: int
    fetched_at: datetime

    @classmethod
    def from_domain(cls, v: AuditView) -> AuditResponse:
        return cls(
            range=v.range,
            items=[
                AuditRecordResponse(
                    ts=a.ts, request_id=a.request_id, event=a.event, actor=a.actor,
                    ip=a.ip,
                    ttl_seconds=a.ttl_seconds, reason=a.reason, result=a.result,
                    status=a.status, error_code=a.error_code, dry_run=a.dry_run,
                )
                for a in v.items
            ],
            count=len(v.items),
            fetched_at=v.fetched_at,
        )


# ── 자동 점검 (firewall-agent design §4.4) ──────────────────────────────


def _as_utc(dt: datetime | None) -> datetime | None:
    """자동 점검 시각(UTC naive)에 +00:00 을 붙인다.

    approval-gate G12 선례.
    """
    if dt is None or dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=UTC)


class AutomationRunResponse(BaseModel):
    status: str
    skip_reason: str | None
    started_at: datetime


class AutomationScheduleResponse(BaseModel):
    id: str
    name: str
    enabled: bool
    cron_expr: str | None
    skip_when_busy: bool
    next_run_at: datetime | None
    last_run: AutomationRunResponse | None


class AutomationAlertResponse(BaseModel):
    configured: bool
    enabled: bool | None
    skip_when_busy: bool | None
    last_result: str | None
    last_received_at: datetime | None


class AutomationAgentResponse(BaseModel):
    id: str
    name: str


class AutomationResponse(BaseModel):
    configured: bool
    reason: str | None = None
    agent: AutomationAgentResponse | None = None
    schedules: list[AutomationScheduleResponse] = []
    alert_receiver: AutomationAlertResponse | None = None

    @classmethod
    def from_domain(cls, state: AutomationState) -> AutomationResponse:
        snap = state.snapshot
        if snap is None:
            return cls(configured=False, reason=state.reason)
        return cls(
            configured=True,
            agent=AutomationAgentResponse(id=snap.agent_id, name=snap.agent_name),
            schedules=[
                AutomationScheduleResponse(
                    id=s.id,
                    name=s.name,
                    enabled=s.enabled,
                    cron_expr=s.cron_expr,
                    skip_when_busy=s.skip_when_busy,
                    next_run_at=_as_utc(s.next_run_at),
                    last_run=(
                        AutomationRunResponse(
                            status=s.last_run.status,
                            skip_reason=s.last_run.skip_reason,
                            started_at=_as_utc(s.last_run.started_at),
                        )
                        if s.last_run
                        else None
                    ),
                )
                for s in snap.schedules
            ],
            alert_receiver=AutomationAlertResponse(
                configured=snap.alert.configured,
                enabled=snap.alert.enabled,
                skip_when_busy=snap.alert.skip_when_busy,
                last_result=snap.alert.last_result,
                last_received_at=_as_utc(snap.alert.last_received_at),
            ),
        )


class AutomationUpdateBody(BaseModel):
    """둘 다 선택. 보낸 항목만 바꾼다."""

    model_config = ConfigDict(extra="forbid")

    schedule_enabled: bool | None = None
    alert_enabled: bool | None = None
