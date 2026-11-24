"""LogQL 템플릿 — 순수 함수.

Design Ref: firewall-admin-console §4.5 — 쿼리는 서버가 만든다. 여기 들어오는
값은 전부 validation.py 를 통과한 것(허용 목록·정규화된 IPv4·허용 문자 actor)이다.
검증 전 문자열을 이 모듈에 넘기지 않는다.
"""
from __future__ import annotations

from src.domain.firewall_admin.models import AuditQuery, EventsQuery

TOP_SOURCES_LIMIT = 10

_RANGE_SECONDS: dict[str, int] = {
    "15m": 900, "1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800,
}


def range_seconds(range_: str) -> int:
    return _RANGE_SECONDS[range_]


def _firewall_selector(action: str) -> str:
    # accept(LAB_ACCEPT 신규 연결 로그)는 조회 대상이 아니다.
    if action == "all":
        return '{job="firewall", action=~"drop|block"}'
    return f'{{job="firewall", action="{action}"}}'


def top_sources(query: EventsQuery) -> str:
    """출발지 IP별 건수 상위 N (순간 쿼리)."""
    return (
        f"topk({TOP_SOURCES_LIMIT}, sum by (src_ip) (count_over_time("
        f'{_firewall_selector(query.action)} | json | __error__="" [{query.range}])))'
    )


def recent_events(query: EventsQuery) -> str:
    """최근 차단 로그 (범위 쿼리). 줄 본문 JSON 은 서버가 파싱하므로 선택자만 쓴다."""
    return _firewall_selector(query.action)


def audit(query: AuditQuery) -> str:
    """fwctl 감사 이력. list·health 는 폴링으로 대량 발생하므로 항상 제외한다."""
    if query.event == "all":
        selector = '{job="fwctl", action=~"block|unblock"}'
    else:
        selector = f'{{job="fwctl", action="{query.event}"}}'
    if query.ip is None and query.actor is None:
        return selector

    parts = [selector, "| json", '| __error__=""']
    if query.ip is not None:
        parts.append(f'| ip="{query.ip}"')
    if query.actor is not None:
        # 허용 문자 중 정규식 메타문자는 '.' 뿐이다. LogQL 큰따옴표 문자열이라 \\. 로 적는다.
        escaped = query.actor.replace(".", "\\\\.")
        parts.append(f'| actor=~".*{escaped}.*"')
    return " ".join(parts)
