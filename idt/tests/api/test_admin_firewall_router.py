"""firewall-admin-console module-1·2 — 라우터 (Design §4, §6.1, §8.2 #15~18).

실제 서비스 + 가짜 포트로 조립한다. 라우트 등록은 TestClient 실요청으로 확인한다.
"""
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.routes import admin_firewall_router as fw_router
from src.application.firewall_admin.control_service import FirewallControlService
from src.application.firewall_admin.observability_service import (
    FirewallObservabilityService,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.firewall_admin.errors import (
    FirewallAdminError,
    ForbiddenWhitelistError,
    FwctlAuditError,
    FwctlAuthFailedError,
    FwctlTimeoutError,
    FwctlUnavailableError,
    GrafanaUnavailableError,
)
from src.domain.firewall_admin.models import (
    AlertInstance,
    AlertRule,
    BlockEntry,
    BlockList,
    BlockResult,
    FwctlHealth,
    LokiLine,
    LokiSample,
    UnblockResult,
)
from src.interfaces.dependencies.auth import get_current_user

BASE = "/api/v1/admin/firewall"
FWCTL_TOKEN = "fwctl-secret-token-value"
GRAFANA_TOKEN = "glsa_secret-token-value"


def _user(role: UserRole, uid: int) -> User:
    return User(email="x@t", password_hash="h", role=role, status=UserStatus.APPROVED, id=uid)


ADMIN = _user(UserRole.ADMIN, 17)
USER = _user(UserRole.USER, 2)


class FakeFwctl:
    token = FWCTL_TOKEN  # 응답에 새어 나가면 안 되는 값

    def __init__(self, *, configured=True, health=None, error=None, absent=False):
        self.configured = configured
        self._health = health or FwctlHealth(
            reachable=True, dry_run=True, max_ttl_seconds=3600, ipset_exists=True,
            version="0.1.0",
        )
        self._error, self._absent = error, absent
        self.block_calls: list[dict] = []
        self.request_ids: list[str] = []

    async def health(self):
        return self._health

    async def list_blocks(self, *, request_id):
        self.request_ids.append(request_id)
        if self._error:
            raise self._error
        return BlockList(items=(BlockEntry("172.28.10.66", 583, 12, 720),), dry_run=True)

    async def block(self, *, ip, ttl_seconds, reason, actor, request_id):
        self.block_calls.append({"ip": ip, "ttl_seconds": ttl_seconds, "reason": reason,
                                 "actor": actor, "request_id": request_id})
        if self._error:
            raise self._error
        return BlockResult(
            ip=ip, ttl_seconds=ttl_seconds or 600,
            expires_at=datetime(2026, 11, 23, 12, 10, 1, tzinfo=UTC),
            reason=reason, dry_run=True, request_id=request_id,
        )

    async def unblock(self, *, ip, request_id):
        self.request_ids.append(request_id)
        if self._error:
            raise self._error
        if self._absent:
            return UnblockResult(ip=ip, removed=False, dry_run=None, already_absent=True)
        return UnblockResult(ip=ip, removed=True, dry_run=False, already_absent=False)


class FakeGrafana:
    configured = True
    token = GRAFANA_TOKEN

    def __init__(self, *, error=None):
        self._error = error
        self.queries: list[str] = []

    async def alert_rules(self):
        if self._error:
            raise self._error
        return (AlertRule(
            uid="fw-r02-port-scan", name="R02 Vertical Port Scan", rule_id="R02",
            kind="port_scan", severity="high", action_hint="block", state="firing",
            description="d", last_evaluation=datetime(2026, 11, 23, 11, 39, 50, tzinfo=UTC),
            instances=(AlertInstance("172.28.10.66", "firing",
                                     datetime(2026, 11, 23, 11, 31, 50, tzinfo=UTC),
                                     "41"),),
        ),)

    async def loki_instant(self, query, *, at_ns):
        self.queries.append(query)
        if self._error:
            raise self._error
        return [LokiSample({"src_ip": "172.28.10.66"}, 182.0)]

    async def loki_range(self, query, *, start_ns, end_ns, limit):
        self.queries.append(query)
        if self._error:
            raise self._error
        if 'job="fwctl"' in query:
            line = ('{"ts":"2026-11-23T11:50:14.703Z","request_id":"adm-17-abc",'
                    '"event":"block","actor":"sangplusbot/admin:17","ip":"172.28.10.66",'
                    '"ttl_seconds":600,"reason":"scan","result":"ok","status":201,'
                    '"error_code":null,"dry_run":true}')
            return [LokiLine(end_ns, {"job": "fwctl", "action": "block"}, line)]
        line = ('{"ip.protocol": 6, "dest_port": 22, "src_ip": "172.28.10.66", '
                '"dest_ip": "172.28.20.10"}')
        return [LokiLine(end_ns, {"job": "firewall", "action": "drop"}, line)]


def _client(user: User | None, fwctl=None, grafana=None) -> tuple[TestClient, FakeFwctl, FakeGrafana]:
    fwctl = fwctl or FakeFwctl()
    grafana = grafana or FakeGrafana()
    logger = MagicMock()
    control = FirewallControlService(
        fwctl, grafana_configured=grafana.configured,
        dashboard_url="http://127.0.0.1:3000/d/fireware-firewall-lab", logger=logger,
    )
    observability = FirewallObservabilityService(grafana, logger=logger)
    app = FastAPI()
    app.include_router(fw_router.router)
    app.dependency_overrides[fw_router.get_control_service] = lambda: control
    app.dependency_overrides[fw_router.get_observability_service] = lambda: observability
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app), fwctl, grafana


BLOCK_BODY = {"ip": "172.28.10.66", "ttl_seconds": 600, "reason": "R02 포트 스캔"}

PATHS = [
    ("get", f"{BASE}/status", None),
    ("get", f"{BASE}/blocks", None),
    ("post", f"{BASE}/blocks", BLOCK_BODY),
    ("delete", f"{BASE}/blocks/172.28.10.66", None),
    ("get", f"{BASE}/alerts", None),
    ("get", f"{BASE}/events", None),
    ("get", f"{BASE}/audit", None),
]


def _call(client: TestClient, method: str, path: str, body):
    return client.request(method.upper(), path, json=body) if body else client.request(
        method.upper(), path
    )


class TestAuth:
    """Plan SC-2 — 7개 경로 전부."""

    @pytest.mark.parametrize("method,path,body", PATHS)
    def test_no_token_401(self, method, path, body):
        client, fwctl, _ = _client(None)
        assert _call(client, method, path, body).status_code == 401
        assert fwctl.block_calls == []

    @pytest.mark.parametrize("method,path,body", PATHS)
    def test_non_admin_403(self, method, path, body):
        client, fwctl, _ = _client(USER)
        assert _call(client, method, path, body).status_code == 403
        assert fwctl.block_calls == [] and fwctl.request_ids == []

    @pytest.mark.parametrize("method,path,body", PATHS)
    def test_admin_2xx(self, method, path, body):
        client, _, _ = _client(ADMIN)
        assert _call(client, method, path, body).status_code in (200, 201)


class TestNoTokenLeak:
    """Plan SC-9 — 응답 본문 어디에도 토큰이 없다."""

    @pytest.mark.parametrize("method,path,body", PATHS)
    def test_success_bodies(self, method, path, body):
        client, _, _ = _client(ADMIN)
        text = _call(client, method, path, body).text
        assert FWCTL_TOKEN not in text and GRAFANA_TOKEN not in text
        assert "token" not in text.lower()

    def test_error_bodies(self):
        client, _, _ = _client(ADMIN, fwctl=FakeFwctl(error=FwctlAuthFailedError()),
                               grafana=FakeGrafana(error=GrafanaUnavailableError()))
        for method, path, body in PATHS:
            text = _call(client, method, path, body).text
            assert FWCTL_TOKEN not in text and GRAFANA_TOKEN not in text


class TestStatus:
    def test_ok(self):
        client, _, _ = _client(ADMIN)
        assert client.get(f"{BASE}/status").json() == {
            "enabled": True,
            "fwctl": {"configured": True, "reachable": True, "dry_run": True,
                      "max_ttl_seconds": 3600, "ipset_exists": True, "version": "0.1.0"},
            "grafana": {"configured": True,
                        "dashboard_url": "http://127.0.0.1:3000/d/fireware-firewall-lab"},
            "default_ttl_seconds": 600,
        }

    def test_fwctl_unreachable_is_still_200(self):
        client, _, _ = _client(ADMIN, fwctl=FakeFwctl(health=FwctlHealth(reachable=False)))
        r = client.get(f"{BASE}/status")
        assert r.status_code == 200
        assert r.json()["fwctl"] == {
            "configured": True, "reachable": False, "dry_run": None,
            "max_ttl_seconds": None, "ipset_exists": None, "version": None,
        }

    def test_not_configured(self):
        client, _, _ = _client(ADMIN, fwctl=FakeFwctl(configured=False))
        assert client.get(f"{BASE}/status").json()["fwctl"]["configured"] is False


class TestBlocks:
    def test_list(self):
        client, fwctl, _ = _client(ADMIN)
        assert client.get(f"{BASE}/blocks").json() == {
            "items": [{"ip": "172.28.10.66", "ttl_remaining_seconds": 583,
                       "packets": 12, "bytes": 720}],
            "count": 1, "dry_run": True,
        }
        assert fwctl.request_ids[0].startswith("adm-17-")

    def test_block_actor_is_server_side(self):
        """Plan SC-4."""
        client, fwctl, _ = _client(ADMIN)
        r = client.post(f"{BASE}/blocks", json=BLOCK_BODY)
        assert r.status_code == 201
        call = fwctl.block_calls[0]
        assert call["actor"] == "sangplusbot/admin:17"
        assert call["request_id"].startswith("adm-17-")
        body = r.json()
        assert body["dry_run"] is True and body["ttl_seconds"] == 600
        assert body["expires_at"].startswith("2026-11-23T12:10:01")
        assert body["request_id"] == call["request_id"]

    def test_block_without_ttl(self):
        client, fwctl, _ = _client(ADMIN)
        r = client.post(f"{BASE}/blocks", json={"ip": "1.2.3.4", "reason": "r"})
        assert r.status_code == 201 and fwctl.block_calls[0]["ttl_seconds"] is None

    def test_actor_in_body_is_rejected(self):
        client, fwctl, _ = _client(ADMIN)
        r = client.post(f"{BASE}/blocks", json={**BLOCK_BODY, "actor": "someone-else"})
        assert r.status_code == 422 and fwctl.block_calls == []
        assert r.json()["detail"]["code"] == "INVALID_REQUEST"
        assert r.json()["detail"]["details"]["field"] == "actor"

    @pytest.mark.parametrize(
        "body,code,field",
        [
            ({"ip": "1.2.3.4", "ttl_seconds": "600", "reason": "r"}, "INVALID_TTL", "ttl_seconds"),
            ({"ip": "1.2.3.4", "ttl_seconds": True, "reason": "r"}, "INVALID_TTL", "ttl_seconds"),
            ({"ip": "1.2.3.4", "ttl_seconds": 60, "reason": 5}, "INVALID_REASON", "reason"),
            ({"ip": "1.2.3.4", "ttl_seconds": 60}, "INVALID_REASON", "reason"),
            ({"ttl_seconds": 60, "reason": "r"}, "INVALID_IP", "ip"),
            ({"ip": 16909060, "reason": "r"}, "INVALID_IP", "ip"),
        ],
    )
    def test_wrong_type_gets_same_error_codes(self, body, code, field):
        """Check G1 — 형이 틀린 입력도 FastAPI 기본 목록이 아니라 같은 코드 형식으로 답한다."""
        client, fwctl, _ = _client(ADMIN)
        r = client.post(f"{BASE}/blocks", json=body)
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert isinstance(detail, dict) and detail["code"] == code
        assert detail["details"]["field"] == field and detail["message"]
        if code == "INVALID_TTL":
            assert detail["details"]["max_ttl_seconds"] == 3600
        assert fwctl.block_calls == []

    def test_non_json_body_is_invalid_request(self):
        client, fwctl, _ = _client(ADMIN)
        r = client.post(
            f"{BASE}/blocks", content=b"not json", headers={"Content-Type": "application/json"}
        )
        assert r.status_code == 422 and r.json()["detail"]["code"] == "INVALID_REQUEST"
        assert fwctl.block_calls == []

    def test_wrong_type_without_token_is_still_401(self):
        client, fwctl, _ = _client(None)
        r = client.post(f"{BASE}/blocks", json={"ip": 1, "ttl_seconds": "x"})
        assert r.status_code == 401 and fwctl.block_calls == []

    @pytest.mark.parametrize(
        "body,code",
        [
            ({"ip": "10.0.0.0/8", "ttl_seconds": 60, "reason": "r"}, "INVALID_IP"),
            ({"ip": "1.2.3.4", "ttl_seconds": 99999, "reason": "r"}, "INVALID_TTL"),
            ({"ip": "1.2.3.4", "ttl_seconds": 60, "reason": "   "}, "INVALID_REASON"),
        ],
    )
    def test_validation_422_with_code(self, body, code):
        """Plan SC-5 (TTL)."""
        client, fwctl, _ = _client(ADMIN)
        r = client.post(f"{BASE}/blocks", json=body)
        assert r.status_code == 422 and r.json()["detail"]["code"] == code
        assert r.json()["detail"]["request_id"].startswith("adm-17-")
        assert fwctl.block_calls == []

    @pytest.mark.parametrize(
        "error,status,code",
        [
            (ForbiddenWhitelistError(details={"matched": "172.28.10.10/32"}), 403,
             "FORBIDDEN_WHITELIST"),
            (FwctlAuthFailedError(), 502, "FWCTL_AUTH_FAILED"),
            (FwctlAuditError(), 502, "FWCTL_AUDIT_ERROR"),
            (FwctlUnavailableError(), 502, "FWCTL_UNAVAILABLE"),
            (FwctlTimeoutError(), 504, "FWCTL_TIMEOUT"),
        ],
    )
    def test_fwctl_errors(self, error: FirewallAdminError, status, code):
        """Plan SC-5 (화이트리스트) 포함."""
        client, _, _ = _client(ADMIN, fwctl=FakeFwctl(error=error))
        r = client.post(f"{BASE}/blocks", json=BLOCK_BODY)
        assert r.status_code == status
        detail = r.json()["detail"]
        assert detail["code"] == code and detail["message"]
        if code == "FORBIDDEN_WHITELIST":
            assert detail["details"]["matched"] == "172.28.10.10/32"

    def test_unblock(self):
        client, fwctl, _ = _client(ADMIN)
        body = client.delete(f"{BASE}/blocks/172.28.10.66").json()
        assert body["removed"] is True and body["already_absent"] is False
        assert body["request_id"] == fwctl.request_ids[0]

    def test_unblock_already_absent(self):
        client, _, _ = _client(ADMIN, fwctl=FakeFwctl(absent=True))
        r = client.delete(f"{BASE}/blocks/1.2.3.4")
        assert r.status_code == 200
        assert r.json()["already_absent"] is True and r.json()["dry_run"] is None

    def test_unblock_invalid_ip(self):
        client, fwctl, _ = _client(ADMIN)
        r = client.delete(f"{BASE}/blocks/not-an-ip")
        assert r.status_code == 422 and r.json()["detail"]["code"] == "INVALID_IP"
        assert fwctl.request_ids == []


class TestObservability:
    def test_alerts(self):
        client, _, _ = _client(ADMIN)
        body = client.get(f"{BASE}/alerts").json()
        assert body["firing_count"] == 1
        rule = body["rules"][0]
        assert (rule["rule_id"], rule["state"], rule["action_hint"]) == ("R02", "firing", "block")
        assert rule["instances"][0]["src_ip"] == "172.28.10.66"
        assert "fetched_at" in body

    def test_events(self):
        client, _, grafana = _client(ADMIN)
        body = client.get(f"{BASE}/events", params={"range": "6h", "action": "drop"}).json()
        assert (body["range"], body["action"]) == ("6h", "drop")
        assert body["top_sources"] == [{"src_ip": "172.28.10.66", "count": 182}]
        assert body["recent"][0]["dport"] == 22 and body["recent"][0]["protocol"] == 6
        assert "[6h]" in grafana.queries[0]

    def test_audit(self):
        client, _, grafana = _client(ADMIN)
        body = client.get(f"{BASE}/audit", params={"ip": "172.28.10.66"}).json()
        assert body["count"] == 1 and body["range"] == "24h"
        assert body["items"][0]["actor"] == "sangplusbot/admin:17"
        assert '| ip="172.28.10.66"' in grafana.queries[0]

    @pytest.mark.parametrize(
        "path,params",
        [
            ("events", {"range": "7d"}),
            ("events", {"action": 'drop"} | x'}),
            ("audit", {"event": "health"}),
            ("audit", {"actor": 'a" | line_format "x'}),
            ("audit", {"ip": "1.2.3"}),
            ("audit", {"limit": 500}),
            # Check G1 — 정수가 아닌 limit 은 FastAPI 가 먼저 막는다. 같은 코드로 답해야 한다.
            ("events", {"limit": "abc"}),
            ("audit", {"limit": "abc"}),
        ],
    )
    def test_invalid_filter_422_and_no_query(self, path, params):
        client, _, grafana = _client(ADMIN)
        r = client.get(f"{BASE}/{path}", params=params)
        assert r.status_code == 422 and r.json()["detail"]["code"] == "INVALID_FILTER"
        assert grafana.queries == []

    @pytest.mark.parametrize("path", ["alerts", "events", "audit"])
    def test_grafana_down_is_503_and_blocks_still_work(self, path):
        """Plan SC-8 — 장애 분리."""
        client, _, _ = _client(ADMIN, grafana=FakeGrafana(error=GrafanaUnavailableError()))
        r = client.get(f"{BASE}/{path}")
        assert r.status_code == 503 and r.json()["detail"]["code"] == "GRAFANA_UNAVAILABLE"
        assert client.get(f"{BASE}/blocks").status_code == 200
        assert client.get(f"{BASE}/status").status_code == 200
