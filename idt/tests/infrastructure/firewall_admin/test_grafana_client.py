"""firewall-admin-console module-2 — GrafanaClient (Design §4.4, §8.2 #10~12).

픽스처는 2026-11-23 Grafana 12.0.0 에 Viewer 서비스 계정 토큰으로 호출한 실제 응답이다.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
from src.domain.firewall_admin.errors import GrafanaUnavailableError
from src.infrastructure.firewall_admin.grafana_client import (
    DETECTION_RULE_GROUP,
    GrafanaClient,
)

FIXTURES = Path(__file__).parents[2] / "fixtures" / "firewall_admin"
TOKEN = "glsa_secret"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _client(handler, token=TOKEN, base_url="http://grafana.test") -> GrafanaClient:
    return GrafanaClient(
        base_url=base_url, token=token, logger=MagicMock(),
        transport=httpx.MockTransport(handler),
    )


class TestRules:
    async def test_parses_real_response(self):
        seen = {}

        def handler(request: httpx.Request):
            seen["path"] = request.url.path
            seen["auth"] = request.headers["authorization"]
            return httpx.Response(200, json=_load("grafana_rules.json"))

        rules = await _client(handler).alert_rules()
        assert seen["path"] == "/api/prometheus/grafana/api/v1/rules"
        assert seen["auth"] == f"Bearer {TOKEN}"
        assert len(rules) == 8
        assert {r.rule_id for r in rules} == {"R01", "R02", "R03", "R04", "R06", "R07", "R08"}
        first = next(r for r in rules if r.uid == "fw-port-scan-suspected")
        assert (first.name, first.kind, first.severity, first.action_hint) == (
            "R01 Drop Burst", "drop_burst", "medium", "block"
        )
        assert first.state == "normal"  # 룰 state "inactive"
        assert first.description and "{{" not in first.description
        assert first.last_evaluation is not None
        assert {i.src_ip for i in first.instances} == {"172.28.10.10"}
        assert all(i.state in {"normal", "nodata"} for i in first.instances)

    async def test_firing_instance(self):
        payload = {"status": "success", "data": {"groups": [{
            "name": DETECTION_RULE_GROUP,
            "rules": [{
                "uid": "fw-r02-port-scan", "name": "R02 Vertical Port Scan",
                "state": "firing", "health": "ok",
                "labels": {"rule_id": "R02", "kind": "port_scan", "severity": "high",
                           "action_hint": "block"},
                "annotations": {"description": "d"},
                "lastEvaluation": "2026-11-23T11:39:50Z",
                "alerts": [{
                    "labels": {"src_ip": "172.28.10.66"}, "state": "Alerting",
                    "activeAt": "2026-11-23T11:31:50Z", "value": "4.1e+01",
                }],
            }],
        }]}}
        rules = await _client(lambda r: httpx.Response(200, json=payload)).alert_rules()
        assert rules[0].state == "firing"
        inst = rules[0].instances[0]
        assert (inst.src_ip, inst.state, inst.value) == ("172.28.10.66", "firing", "4.1e+01")
        assert inst.active_at.isoformat() == "2026-11-23T11:31:50+00:00"

    async def test_unhealthy_rule_is_error(self):
        payload = {"status": "success", "data": {"groups": [{
            "name": DETECTION_RULE_GROUP,
            "rules": [{"uid": "u", "name": "n", "state": "inactive", "health": "error",
                       "labels": {}, "annotations": {}, "alerts": []}],
        }]}}
        rules = await _client(lambda r: httpx.Response(200, json=payload)).alert_rules()
        assert rules[0].state == "error"
        assert rules[0].rule_id == "" and rules[0].last_evaluation is None

    @pytest.mark.parametrize(
        "response",
        [
            httpx.Response(200, json={"status": "success", "data": {"groups": []}}),
            httpx.Response(200, json={"status": "success", "data": {"groups": [
                {"name": "other", "rules": []}]}}),
            httpx.Response(200, json={"status": "error"}),
            httpx.Response(200, text="<html>login</html>"),
            httpx.Response(200, json=[1, 2]),
            httpx.Response(401, json={"message": "Unauthorized"}),
            httpx.Response(403, json={"message": "Forbidden"}),
            httpx.Response(500, text="boom"),
        ],
    )
    async def test_failures_are_unavailable(self, response):
        with pytest.raises(GrafanaUnavailableError):
            await _client(lambda r: response).alert_rules()

    async def test_timeout(self):
        def handler(request):
            raise httpx.ReadTimeout("slow", request=request)

        with pytest.raises(GrafanaUnavailableError):
            await _client(handler).alert_rules()

    async def test_connect_error(self):
        def handler(request):
            raise httpx.ConnectError("refused", request=request)

        with pytest.raises(GrafanaUnavailableError):
            await _client(handler).alert_rules()

    @pytest.mark.parametrize("token,base_url", [("", "http://g"), (TOKEN, "")])
    async def test_not_configured_sends_nothing(self, token, base_url):
        calls = []

        def handler(request):
            calls.append(1)
            return httpx.Response(200, json={})

        client = _client(handler, token=token, base_url=base_url)
        assert client.configured is False
        with pytest.raises(GrafanaUnavailableError):
            await client.alert_rules()
        assert calls == []


class TestLokiInstant:
    async def test_parses_real_vector(self):
        seen = {}

        def handler(request):
            seen["path"] = request.url.path
            seen["params"] = dict(request.url.params)
            return httpx.Response(200, json=_load("loki_vector.json"))

        samples = await _client(handler).loki_instant("QUERY", at_ns=1795434884000000000)
        assert seen["path"] == "/api/datasources/proxy/uid/loki/loki/api/v1/query"
        assert seen["params"] == {"query": "QUERY", "time": "1795434884000000000"}
        assert [(s.labels, s.value) for s in samples] == [({"src_ip": "172.28.10.10"}, 2.0)]

    async def test_wrong_result_type(self):
        resp = httpx.Response(200, json={"status": "success",
                                         "data": {"resultType": "streams", "result": []}})
        with pytest.raises(GrafanaUnavailableError):
            await _client(lambda r: resp).loki_instant("Q", at_ns=1)

    async def test_empty(self):
        resp = httpx.Response(200, json={"status": "success",
                                         "data": {"resultType": "vector", "result": []}})
        assert await _client(lambda r: resp).loki_instant("Q", at_ns=1) == []


class TestLokiRange:
    async def test_parses_real_streams(self):
        seen = {}

        def handler(request):
            seen["path"] = request.url.path
            seen["params"] = dict(request.url.params)
            return httpx.Response(200, json=_load("loki_streams_firewall.json"))

        lines = await _client(handler).loki_range("Q", start_ns=10, end_ns=20, limit=3)
        assert seen["path"] == "/api/datasources/proxy/uid/loki/loki/api/v1/query_range"
        assert seen["params"] == {
            "query": "Q", "start": "10", "end": "20", "limit": "3", "direction": "backward",
        }
        assert len(lines) >= 1
        first = lines[0]
        assert first.labels["job"] == "firewall" and first.labels["action"] == "drop"
        assert json.loads(first.line)["dest_port"] == 22
        assert first.ts_ns > 1_700_000_000_000_000_000

    async def test_sorted_newest_first_across_streams(self):
        payload = {"status": "success", "data": {"resultType": "streams", "result": [
            {"stream": {"action": "drop"}, "values": [["300", "c"], ["100", "a"]]},
            {"stream": {"action": "block"}, "values": [["200", "b"]]},
        ]}}
        lines = await _client(lambda r: httpx.Response(200, json=payload)).loki_range(
            "Q", start_ns=0, end_ns=400, limit=2
        )
        assert [(x.ts_ns, x.line, x.labels["action"]) for x in lines] == [
            (300, "c", "drop"), (200, "b", "block"),
        ]

    async def test_wrong_result_type(self):
        resp = httpx.Response(200, json={"status": "success",
                                         "data": {"resultType": "matrix", "result": []}})
        with pytest.raises(GrafanaUnavailableError):
            await _client(lambda r: resp).loki_range("Q", start_ns=0, end_ns=1, limit=1)

    async def test_bad_gateway(self):
        with pytest.raises(GrafanaUnavailableError):
            await _client(lambda r: httpx.Response(502, text="loki down")).loki_range(
                "Q", start_ns=0, end_ns=1, limit=1
            )


async def test_aclose():
    await _client(lambda r: httpx.Response(200, json={})).aclose()
