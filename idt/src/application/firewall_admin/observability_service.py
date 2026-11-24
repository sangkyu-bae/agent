"""탐지 알림·차단 로그·감사 이력 조회.

Design Ref: firewall-admin-console §4.2, §4.5 — 조회 조건은 검증을 통과한 값만
LogQL 템플릿에 넣는다. Grafana 장애는 GrafanaUnavailableError 로 그대로 올린다
(현황 탭은 fwctl 만 쓰므로 영향받지 않는다 — Plan SC-8).
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from src.application.firewall_admin.ports import GrafanaPort
from src.domain.firewall_admin import logql
from src.domain.firewall_admin.models import (
    ALERT_STATE_ORDER,
    AlertInstance,
    AlertRule,
    AuditRecord,
    FirewallEvent,
    LokiLine,
    SourceCount,
)
from src.domain.firewall_admin.validation import (
    validate_audit_query,
    validate_events_query,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface

# 발화가 끝난 과거 출발지 IP 가 룰마다 계속 쌓이므로 조용한 인스턴스는 일부만 싣는다.
MAX_QUIET_INSTANCES = 5
_ACTIVE_STATES = ("firing", "pending", "error")
_NS = 1_000_000_000
_EPOCH = datetime.fromtimestamp(0, tz=UTC)


@dataclass(frozen=True)
class AlertsView:
    rules: tuple[AlertRule, ...]
    firing_count: int
    fetched_at: datetime


@dataclass(frozen=True)
class EventsView:
    range: str
    action: str
    top_sources: tuple[SourceCount, ...]
    recent: tuple[FirewallEvent, ...]
    fetched_at: datetime


@dataclass(frozen=True)
class AuditView:
    range: str
    items: tuple[AuditRecord, ...]
    fetched_at: datetime


def _from_ns(ts_ns: int) -> datetime:
    return datetime.fromtimestamp(ts_ns / _NS, tz=UTC)


def _typed(value: Any, kind: type) -> Any:
    """기대한 형이 아니면 None. bool 은 int 로 취급하지 않는다."""
    if kind is int and isinstance(value, bool):
        return None
    return value if isinstance(value, kind) else None


def _trim_instances(instances: tuple[AlertInstance, ...]) -> tuple[AlertInstance, ...]:
    ordered = sorted(
        instances,
        key=lambda i: (ALERT_STATE_ORDER[i.state], -(i.active_at or _EPOCH).timestamp()),
    )
    active = [i for i in ordered if i.state in _ACTIVE_STATES]
    quiet = [i for i in ordered if i.state not in _ACTIVE_STATES][:MAX_QUIET_INSTANCES]
    return tuple(sorted(active + quiet, key=lambda i: ALERT_STATE_ORDER[i.state]))


class FirewallObservabilityService:
    def __init__(
        self,
        grafana: GrafanaPort,
        *,
        logger: LoggerInterface,
        now_ns: Callable[[], int] = time.time_ns,
    ) -> None:
        self._grafana = grafana
        self._logger = logger
        self._now_ns = now_ns

    async def alerts(self) -> AlertsView:
        rules = await self._grafana.alert_rules()
        trimmed = [replace(r, instances=_trim_instances(r.instances)) for r in rules]
        trimmed.sort(key=lambda r: (ALERT_STATE_ORDER[r.state], r.rule_id, r.uid))
        firing = sum(1 for r in trimmed for i in r.instances if i.state == "firing")
        return AlertsView(
            rules=tuple(trimmed), firing_count=firing, fetched_at=_from_ns(self._now_ns())
        )

    async def events(self, *, range_: object, action: object, limit: object) -> EventsView:
        query = validate_events_query(range_, action, limit)
        now = self._now_ns()
        samples = await self._grafana.loki_instant(logql.top_sources(query), at_ns=now)
        lines = await self._grafana.loki_range(
            logql.recent_events(query),
            start_ns=now - logql.range_seconds(query.range) * _NS,
            end_ns=now,
            limit=query.limit,
        )
        top = sorted(
            (
                SourceCount(src_ip=s.labels["src_ip"], count=int(s.value))
                for s in samples
                if s.labels.get("src_ip")
            ),
            key=lambda s: (-s.count, s.src_ip),
        )
        recent = self._parse_lines(lines, self._event, "firewall_admin.events_bad_lines")
        return EventsView(
            range=query.range, action=query.action, top_sources=tuple(top),
            recent=tuple(recent), fetched_at=_from_ns(now),
        )

    async def audit(
        self, *, range_: object, event: object, ip: object, actor: object, limit: object
    ) -> AuditView:
        query = validate_audit_query(range_, event, ip, actor, limit)
        now = self._now_ns()
        lines = await self._grafana.loki_range(
            logql.audit(query),
            start_ns=now - logql.range_seconds(query.range) * _NS,
            end_ns=now,
            limit=query.limit,
        )
        items = self._parse_lines(lines, self._audit_record, "firewall_admin.audit_bad_lines")
        return AuditView(range=query.range, items=tuple(items), fetched_at=_from_ns(now))

    # ── 줄 파싱 ───────────────────────────────────────────────────

    def _parse_lines(self, lines: list[LokiLine], build: Callable, log_key: str) -> list:
        parsed, skipped = [], 0
        for line in lines:
            try:
                body = json.loads(line.line)
            except ValueError:
                skipped += 1
                continue
            if not isinstance(body, dict):
                skipped += 1
                continue
            parsed.append(build(line, body))
        if skipped:
            self._logger.warning(log_key, skipped=skipped, total=len(lines))
        return parsed

    @staticmethod
    def _event(line: LokiLine, body: dict[str, Any]) -> FirewallEvent:
        # ulogd JSON 실측 키: src_ip, dest_ip, ip.protocol, dest_port (TCP·UDP 공통)
        return FirewallEvent(
            ts=_from_ns(line.ts_ns),
            action=line.labels.get("action") or "",
            src_ip=_typed(body.get("src_ip"), str),
            dest_ip=_typed(body.get("dest_ip"), str),
            protocol=_typed(body.get("ip.protocol"), int),
            dport=_typed(body.get("dest_port"), int),
        )

    @staticmethod
    def _audit_record(line: LokiLine, body: dict[str, Any]) -> AuditRecord:
        ts = _from_ns(line.ts_ns)
        raw_ts = body.get("ts")
        if isinstance(raw_ts, str):
            try:
                ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            except ValueError:
                pass
        return AuditRecord(
            ts=ts,
            request_id=_typed(body.get("request_id"), str),
            event=_typed(body.get("event"), str),
            actor=_typed(body.get("actor"), str),
            ip=_typed(body.get("ip"), str),
            ttl_seconds=_typed(body.get("ttl_seconds"), int),
            reason=_typed(body.get("reason"), str),
            result=_typed(body.get("result"), str),
            status=_typed(body.get("status"), int),
            error_code=_typed(body.get("error_code"), str),
            dry_run=_typed(body.get("dry_run"), bool),
        )
