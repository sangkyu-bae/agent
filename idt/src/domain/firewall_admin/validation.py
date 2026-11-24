"""입력 검증 — 순수 함수, 표준 라이브러리만.

Design Ref: firewall-admin-console §4.2, §7 — idt 는 형식만 본다. 화이트리스트·
실제 TTL 상한·dry-run 판정은 fwctl 이 강제하고 여기서는 복제하지 않는다.
조회 필터는 LogQL 템플릿에 들어가는 값이므로 허용 목록·정규식으로만 통과시킨다.
"""
from __future__ import annotations

import ipaddress
import re

from src.domain.firewall_admin.errors import (
    InvalidFilterError,
    InvalidIpError,
    InvalidReasonError,
    InvalidTtlError,
)
from src.domain.firewall_admin.models import AuditQuery, BlockRequest, EventsQuery

# fwctl 계약(docs/fwctl-api.md v0.1.0)의 기본 상한과 같다. 실제 상한은 fwctl 이 강제한다.
MAX_TTL_SECONDS = 3600
MAX_REASON_CHARS = 500

EVENT_RANGES: tuple[str, ...] = ("15m", "1h", "6h", "24h")
EVENT_ACTIONS: tuple[str, ...] = ("all", "drop", "block")
AUDIT_RANGES: tuple[str, ...] = ("1h", "6h", "24h", "7d")
AUDIT_EVENTS: tuple[str, ...] = ("all", "block", "unblock")
MAX_LIMIT = 200

_ACTOR_RE = re.compile(r"[A-Za-z0-9._:/-]{1,100}")
# 영숫자가 하나도 없는 값(".*" 등)은 필터로서 의미가 없고 정규식 조각으로 읽힐 수 있다.
_HAS_ALNUM_RE = re.compile(r"[A-Za-z0-9]")


def normalize_ipv4(raw: object) -> str:
    """IPv4 단일 주소만 통과. CIDR·IPv6·호스트명 거부."""
    if not isinstance(raw, str):
        raise InvalidIpError(details={"ip": None})
    text = raw.strip()
    try:
        return str(ipaddress.IPv4Address(text))
    except ValueError as e:
        raise InvalidIpError(details={"ip": text[:64]}) from e


def _validate_ttl(ttl: object) -> int | None:
    if ttl is None:
        return None
    # bool 은 int 의 하위형이라 따로 막는다.
    if isinstance(ttl, bool) or not isinstance(ttl, int) or not 1 <= ttl <= MAX_TTL_SECONDS:
        raise InvalidTtlError(
            f"유지 시간은 1~{MAX_TTL_SECONDS}초입니다",
            details={"max_ttl_seconds": MAX_TTL_SECONDS},
        )
    return ttl


def _validate_reason(reason: object) -> str:
    if not isinstance(reason, str):
        raise InvalidReasonError()
    text = reason.strip()
    if not 1 <= len(text) <= MAX_REASON_CHARS:
        raise InvalidReasonError()
    return text


def validate_block_request(ip: object, ttl_seconds: object, reason: object) -> BlockRequest:
    """검증 순서: ip → ttl → reason (mcp-firewall-server 와 같은 순서)."""
    return BlockRequest(
        ip=normalize_ipv4(ip),
        ttl_seconds=_validate_ttl(ttl_seconds),
        reason=_validate_reason(reason),
    )


def _choice(value: object, allowed: tuple[str, ...], default: str, field: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str) or value not in allowed:
        raise InvalidFilterError(details={"field": field, "allowed": list(allowed)})
    return value


def _limit(value: object, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_LIMIT:
        raise InvalidFilterError(details={"field": "limit", "max": MAX_LIMIT})
    return value


def validate_events_query(range_: object, action: object, limit: object) -> EventsQuery:
    return EventsQuery(
        range=_choice(range_, EVENT_RANGES, "1h", "range"),
        action=_choice(action, EVENT_ACTIONS, "all", "action"),
        limit=_limit(limit, 50),
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidFilterError()
    return value.strip() or None


def validate_audit_query(
    range_: object, event: object, ip: object, actor: object, limit: object
) -> AuditQuery:
    ip_text = _optional_text(ip)
    if ip_text is not None:
        try:
            ip_text = normalize_ipv4(ip_text)
        except InvalidIpError as e:
            raise InvalidFilterError(details={"field": "ip"}) from e

    actor_text = _optional_text(actor)
    if actor_text is not None and (
        not _ACTOR_RE.fullmatch(actor_text) or not _HAS_ALNUM_RE.search(actor_text)
    ):
        raise InvalidFilterError(details={"field": "actor"})

    return AuditQuery(
        range=_choice(range_, AUDIT_RANGES, "24h", "range"),
        event=_choice(event, AUDIT_EVENTS, "all", "event"),
        ip=ip_text,
        actor=actor_text,
        limit=_limit(limit, 100),
    )
