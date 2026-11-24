"""firewall-admin-console module-2 — LogQL 템플릿 (Design §4.5, §8.2 #5·#6).

쿼리는 서버가 고정 템플릿으로만 만든다. 생성 문자열을 그대로 고정한다.
"""
from src.domain.firewall_admin import logql
from src.domain.firewall_admin.models import (
    AuditQuery,
    EventsQuery,
    normalize_alert_state,
)


def _events(action="all", rng="1h"):
    return EventsQuery(range=rng, action=action, limit=50)


def test_top_sources_all():
    assert logql.top_sources(_events()) == (
        'topk(10, sum by (src_ip) (count_over_time('
        '{job="firewall", action=~"drop|block"} | json | __error__="" [1h])))'
    )


def test_top_sources_single_action_and_range():
    assert logql.top_sources(_events("block", "24h")) == (
        'topk(10, sum by (src_ip) (count_over_time('
        '{job="firewall", action="block"} | json | __error__="" [24h])))'
    )


def test_recent_events_selector_only():
    assert logql.recent_events(_events()) == '{job="firewall", action=~"drop|block"}'
    assert logql.recent_events(_events("drop")) == '{job="firewall", action="drop"}'


def _audit(event="all", ip=None, actor=None):
    return AuditQuery(range="24h", event=event, ip=ip, actor=actor, limit=100)


def test_audit_all_excludes_list_and_health():
    assert logql.audit(_audit()) == '{job="fwctl", action=~"block|unblock"}'


def test_audit_single_event():
    assert logql.audit(_audit("unblock")) == '{job="fwctl", action="unblock"}'


def test_audit_ip_filter():
    assert logql.audit(_audit(ip="172.28.10.66")) == (
        '{job="fwctl", action=~"block|unblock"} | json | __error__="" | ip="172.28.10.66"'
    )


def test_audit_actor_filter_escapes_dot():
    # LogQL 큰따옴표 문자열 안에서 정규식 \. 은 \\. 로 적는다.
    assert logql.audit(_audit(actor="sangplusbot/admin:1.7")) == (
        '{job="fwctl", action=~"block|unblock"} | json | __error__="" '
        '| actor=~".*sangplusbot/admin:1\\\\.7.*"'
    )


def test_audit_both_filters():
    q = logql.audit(_audit("block", ip="1.2.3.4", actor="mcp-firewall-server"))
    assert q == (
        '{job="fwctl", action="block"} | json | __error__="" '
        '| ip="1.2.3.4" | actor=~".*mcp-firewall-server.*"'
    )


def test_range_seconds():
    assert logql.range_seconds("15m") == 900
    assert logql.range_seconds("7d") == 604800


class TestAlertState:
    def test_instance_states(self):
        assert normalize_alert_state("Alerting") == "firing"
        assert normalize_alert_state("Pending") == "pending"
        assert normalize_alert_state("Normal") == "normal"
        assert normalize_alert_state("Normal (NoData)") == "nodata"
        assert normalize_alert_state("NoData") == "nodata"
        assert normalize_alert_state("Normal (Error)") == "error"
        assert normalize_alert_state("Error") == "error"

    def test_rule_states(self):
        assert normalize_alert_state("firing") == "firing"
        assert normalize_alert_state("pending") == "pending"
        assert normalize_alert_state("inactive") == "normal"

    def test_unknown_is_error(self):
        assert normalize_alert_state("weird") == "error"
        assert normalize_alert_state(None) == "error"
