"""firewall-admin-console module-2 — FirewallObservabilityService (Design §4.2, §8.2 #12·#13)."""
import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from src.application.firewall_admin.observability_service import (
    MAX_QUIET_INSTANCES,
    FirewallObservabilityService,
)
from src.domain.firewall_admin.errors import GrafanaUnavailableError, InvalidFilterError
from src.domain.firewall_admin.models import (
    AlertInstance,
    AlertRule,
    LokiLine,
    LokiSample,
)

NOW_NS = 1_795_434_884_000_000_000


class FakeGrafana:
    configured = True

    def __init__(self, *, rules=(), samples=(), lines=(), error=None):
        self._rules, self._samples, self._lines, self._error = rules, samples, lines, error
        self.calls: list[tuple[str, dict]] = []

    async def alert_rules(self):
        self.calls.append(("rules", {}))
        if self._error:
            raise self._error
        return tuple(self._rules)

    async def loki_instant(self, query, *, at_ns):
        self.calls.append(("instant", {"query": query, "at_ns": at_ns}))
        if self._error:
            raise self._error
        return list(self._samples)

    async def loki_range(self, query, *, start_ns, end_ns, limit):
        self.calls.append(("range", {
            "query": query, "start_ns": start_ns, "end_ns": end_ns, "limit": limit,
        }))
        if self._error:
            raise self._error
        return list(self._lines)


def _service(grafana):
    logger = MagicMock()
    return FirewallObservabilityService(grafana, logger=logger, now_ns=lambda: NOW_NS), logger


def _inst(ip, state, minute=0):
    return AlertInstance(
        src_ip=ip, state=state,
        active_at=datetime(2026, 11, 23, 11, minute, tzinfo=UTC), value=None,
    )


def _rule(rule_id, state, instances=()):
    return AlertRule(
        uid=f"uid-{rule_id}-{state}", name=f"{rule_id} name", rule_id=rule_id, kind="k",
        severity="high", action_hint="block", state=state, description="d",
        last_evaluation=None, instances=tuple(instances),
    )


class TestAlerts:
    async def test_sorted_firing_first_then_rule_id(self):
        grafana = FakeGrafana(rules=[
            _rule("R07", "normal"), _rule("R02", "firing"), _rule("R01", "pending"),
            _rule("R04", "error"), _rule("R03", "nodata"), _rule("R01", "firing"),
        ])
        service, _ = _service(grafana)
        view = await service.alerts()
        assert [(r.rule_id, r.state) for r in view.rules] == [
            ("R01", "firing"), ("R02", "firing"), ("R01", "pending"), ("R04", "error"),
            ("R03", "nodata"), ("R07", "normal"),
        ]
        assert view.fetched_at == datetime.fromtimestamp(NOW_NS / 1e9, tz=UTC)

    async def test_instances_sorted_and_quiet_ones_capped(self):
        quiet = [_inst(f"10.0.0.{i}", "nodata", i) for i in range(7)]
        instances = quiet[:3] + [_inst("172.28.10.66", "firing"),
                                 _inst("172.28.10.67", "pending")] + quiet[3:]
        service, _ = _service(FakeGrafana(rules=[_rule("R02", "firing", instances)]))
        rule = (await service.alerts()).rules[0]
        assert [i.state for i in rule.instances[:2]] == ["firing", "pending"]
        quiet_kept = [i for i in rule.instances if i.state == "nodata"]
        assert len(quiet_kept) == MAX_QUIET_INSTANCES == 5
        # 조용한 인스턴스는 최근 것부터 남긴다
        assert quiet_kept[0].src_ip == "10.0.0.6"

    async def test_firing_count_counts_instances(self):
        service, _ = _service(FakeGrafana(rules=[
            _rule("R01", "firing", [_inst("a", "firing"), _inst("b", "firing")]),
            _rule("R02", "firing", [_inst("a", "firing"), _inst("c", "pending")]),
            _rule("R03", "normal", [_inst("d", "normal")]),
        ]))
        assert (await service.alerts()).firing_count == 3

    async def test_grafana_failure_propagates(self):
        service, _ = _service(FakeGrafana(error=GrafanaUnavailableError()))
        with pytest.raises(GrafanaUnavailableError):
            await service.alerts()


def _fw_line(ts_ns, action="drop", **overrides):
    body = {
        "timestamp": "2026-11-23T11:51:28.690412", "oob.prefix": "LAB_DROP ",
        "ip.protocol": 6, "src_port": 46982, "dest_port": 22,
        "src_ip": "172.28.10.10", "dest_ip": "172.28.20.10",
    }
    body.update(overrides)
    return LokiLine(ts_ns=ts_ns, labels={"job": "firewall", "action": action},
                    line=json.dumps(body))


class TestEvents:
    async def test_queries_and_parsing(self):
        grafana = FakeGrafana(
            samples=[
                LokiSample({"src_ip": "172.28.10.10"}, 2.0),
                LokiSample({"src_ip": "172.28.10.66"}, 182.0),
                LokiSample({}, 5.0),  # src_ip 없는 시리즈는 버린다
            ],
            lines=[_fw_line(NOW_NS - 1_000_000_000), _fw_line(NOW_NS - 2_000_000_000, "block")],
        )
        service, _ = _service(grafana)
        view = await service.events(range_="1h", action="all", limit=50)

        instant, rng = grafana.calls
        assert instant[0] == "instant" and instant[1]["at_ns"] == NOW_NS
        assert "topk(10" in instant[1]["query"] and "[1h]" in instant[1]["query"]
        assert rng[1] == {
            "query": '{job="firewall", action=~"drop|block"}',
            "start_ns": NOW_NS - 3600 * 1_000_000_000, "end_ns": NOW_NS, "limit": 50,
        }
        assert [(s.src_ip, s.count) for s in view.top_sources] == [
            ("172.28.10.66", 182), ("172.28.10.10", 2),
        ]
        first = view.recent[0]
        assert (first.action, first.src_ip, first.dest_ip, first.protocol, first.dport) == (
            "drop", "172.28.10.10", "172.28.20.10", 6, 22
        )
        assert first.ts == datetime.fromtimestamp((NOW_NS - 1_000_000_000) / 1e9, tz=UTC)
        assert view.recent[1].action == "block"
        assert (view.range, view.action) == ("1h", "all")

    async def test_icmp_has_no_port(self):
        line = _fw_line(NOW_NS, **{"ip.protocol": 1})
        body = json.loads(line.line)
        del body["dest_port"], body["src_port"]
        grafana = FakeGrafana(lines=[LokiLine(line.ts_ns, line.labels, json.dumps(body))])
        service, _ = _service(grafana)
        event = (await service.events(range_=None, action=None, limit=None)).recent[0]
        assert event.protocol == 1 and event.dport is None

    async def test_bad_lines_are_skipped_with_warning(self):
        grafana = FakeGrafana(lines=[
            _fw_line(NOW_NS), LokiLine(NOW_NS - 1, {"action": "drop"}, "not json"),
            LokiLine(NOW_NS - 2, {"action": "drop"}, "[1, 2]"),
        ])
        service, logger = _service(grafana)
        view = await service.events(range_="15m", action="drop", limit=10)
        assert len(view.recent) == 1
        assert logger.warning.call_args.kwargs["skipped"] == 2

    async def test_invalid_filter_never_reaches_grafana(self):
        grafana = FakeGrafana()
        service, _ = _service(grafana)
        with pytest.raises(InvalidFilterError):
            await service.events(range_='1h"} | x', action="all", limit=10)
        assert grafana.calls == []


def _audit_line(ts_ns, **overrides):
    body = {
        "ts": "2026-11-23T11:50:14.703Z", "request_id": "adm-17-abc", "event": "block",
        "actor": "sangplusbot/admin:17", "client_addr": "172.28.20.1", "method": "POST",
        "path": "/v1/blocks", "ip": "172.28.10.66", "ttl_seconds": 600, "reason": "scan",
        "result": "ok", "status": 201, "error_code": None, "dry_run": True,
    }
    body.update(overrides)
    return LokiLine(ts_ns=ts_ns, labels={"job": "fwctl", "action": body["event"]},
                    line=json.dumps(body))


class TestAudit:
    async def test_query_and_parsing(self):
        grafana = FakeGrafana(lines=[
            _audit_line(NOW_NS),
            _audit_line(NOW_NS - 5, event="unblock", actor=None, ttl_seconds=None,
                        reason=None, status=200, request_id="adm-17-def"),
        ])
        service, _ = _service(grafana)
        view = await service.audit(range_="7d", event="all", ip=" 172.28.10.66 ",
                                   actor=None, limit=20)
        call = grafana.calls[0]
        assert call[0] == "range"
        assert call[1]["query"] == (
            '{job="fwctl", action=~"block|unblock"} | json | __error__="" '
            '| ip="172.28.10.66"'
        )
        assert call[1]["start_ns"] == NOW_NS - 604800 * 1_000_000_000
        assert call[1]["limit"] == 20
        first, second = view.items
        assert (first.event, first.actor, first.ip, first.ttl_seconds, first.reason,
                first.result, first.status, first.error_code, first.dry_run,
                first.request_id) == (
            "block", "sangplusbot/admin:17", "172.28.10.66", 600, "scan", "ok", 201, None,
            True, "adm-17-abc",
        )
        assert first.ts.isoformat() == "2026-11-23T11:50:14.703000+00:00"
        assert (second.event, second.actor, second.request_id) == (
            "unblock", None, "adm-17-def"
        )
        assert view.range == "7d"

    async def test_ts_falls_back_to_loki_timestamp(self):
        grafana = FakeGrafana(lines=[_audit_line(NOW_NS, ts="garbage")])
        service, _ = _service(grafana)
        record = (await service.audit(range_=None, event=None, ip=None, actor=None,
                                      limit=None)).items[0]
        assert record.ts == datetime.fromtimestamp(NOW_NS / 1e9, tz=UTC)

    async def test_wrong_typed_fields_become_none(self):
        grafana = FakeGrafana(lines=[_audit_line(NOW_NS, status="201", dry_run="yes",
                                                 ttl_seconds="600", actor=17)])
        service, _ = _service(grafana)
        record = (await service.audit(range_=None, event=None, ip=None, actor=None,
                                      limit=None)).items[0]
        assert (record.status, record.dry_run, record.ttl_seconds, record.actor) == (
            None, None, None, None
        )

    async def test_injection_attempt_rejected_before_query(self):
        grafana = FakeGrafana()
        service, _ = _service(grafana)
        with pytest.raises(InvalidFilterError):
            await service.audit(range_="24h", event="all", ip=None,
                                actor='x" | line_format "{{.reason}}', limit=10)
        assert grafana.calls == []
