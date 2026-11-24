"""firewall_admin 전달 객체. DB 테이블은 없다.

Design Ref: firewall-admin-console §3.1.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

AlertState = Literal["firing", "pending", "normal", "nodata", "error"]

# 정렬 순서: 발화 → 대기 → 오류 → 나머지 (Design §4.2 alerts)
ALERT_STATE_ORDER: dict[str, int] = {
    "firing": 0, "pending": 1, "error": 2, "nodata": 3, "normal": 4,
}

_ALERT_STATE_MAP: dict[str, AlertState] = {
    # 인스턴스 상태 (Grafana 12.0.0 실측)
    "alerting": "firing",
    "pending": "pending",
    "normal": "normal",
    "normal (nodata)": "nodata",
    "nodata": "nodata",
    "normal (error)": "error",
    "error": "error",
    # 룰 상태
    "firing": "firing",
    "inactive": "normal",
}


def normalize_alert_state(raw: object) -> AlertState:
    """Grafana 원문 상태 → 화면용 5종. 모르는 값은 error 로 드러낸다."""
    if not isinstance(raw, str):
        return "error"
    return _ALERT_STATE_MAP.get(raw.strip().lower(), "error")


@dataclass(frozen=True)
class BlockRequest:
    ip: str
    ttl_seconds: int | None
    reason: str


@dataclass(frozen=True)
class BlockEntry:
    ip: str
    ttl_remaining_seconds: int
    packets: int
    bytes: int


@dataclass(frozen=True)
class BlockList:
    items: tuple[BlockEntry, ...]
    dry_run: bool


@dataclass(frozen=True)
class BlockResult:
    ip: str
    ttl_seconds: int
    expires_at: datetime
    reason: str
    dry_run: bool
    request_id: str


@dataclass(frozen=True)
class UnblockResult:
    ip: str
    removed: bool
    dry_run: bool | None
    already_absent: bool


@dataclass(frozen=True)
class FwctlHealth:
    reachable: bool
    dry_run: bool | None = None
    max_ttl_seconds: int | None = None
    ipset_exists: bool | None = None
    version: str | None = None


@dataclass(frozen=True)
class AlertInstance:
    src_ip: str | None
    state: AlertState
    active_at: datetime | None
    value: str | None


@dataclass(frozen=True)
class AlertRule:
    uid: str
    name: str
    rule_id: str
    kind: str
    severity: str
    action_hint: str
    state: AlertState
    description: str
    last_evaluation: datetime | None
    instances: tuple[AlertInstance, ...]


@dataclass(frozen=True)
class LokiSample:
    """순간 쿼리 결과 1건 (vector)."""

    labels: dict[str, str]
    value: float


@dataclass(frozen=True)
class LokiLine:
    """범위 쿼리 결과 1줄 (streams)."""

    ts_ns: int
    labels: dict[str, str]
    line: str


@dataclass(frozen=True)
class SourceCount:
    src_ip: str
    count: int


@dataclass(frozen=True)
class FirewallEvent:
    ts: datetime
    action: str
    src_ip: str | None
    dest_ip: str | None
    protocol: int | None
    dport: int | None


@dataclass(frozen=True)
class AuditRecord:
    ts: datetime
    request_id: str | None
    event: str | None
    actor: str | None
    ip: str | None
    ttl_seconds: int | None
    reason: str | None
    result: str | None
    status: int | None
    error_code: str | None
    dry_run: bool | None


@dataclass(frozen=True)
class EventsQuery:
    range: str
    action: str
    limit: int


@dataclass(frozen=True)
class AuditQuery:
    range: str
    event: str
    ip: str | None
    actor: str | None
    limit: int
