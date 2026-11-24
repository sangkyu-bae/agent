"""firewall-admin-console module-1 — 조립·킬스위치 (Design §6.3, §8.2 #19·#20).

- enabled=False → 부품 None, 라우트 없음(404)  [Plan SC-1]
- enabled=True, 토큰 없음 → 라우트 등록, warning, configured=False
- 조립 실패 → None + warning (앱 기동은 계속)
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api import firewall_admin_di as di
from src.domain.auth.entities import User, UserRole, UserStatus
from src.interfaces.dependencies.auth import get_current_user

STATUS = "/api/v1/admin/firewall/status"


def _settings(enabled=True, fwctl_token="t", grafana_token="g",
              fwctl_url="http://127.0.0.1:8070", grafana_url="http://127.0.0.1:3000/"):
    return SimpleNamespace(
        firewall_admin_enabled=enabled,
        firewall_admin_fwctl_url=fwctl_url,
        firewall_admin_fwctl_token=fwctl_token,
        firewall_admin_grafana_url=grafana_url,
        firewall_admin_grafana_token=grafana_token,
    )


def _warnings(logger) -> list[str]:
    return [c.args[0] for c in logger.warning.call_args_list]


def test_disabled_builds_nothing_and_logs_nothing():
    logger = MagicMock()
    assert di.build_firewall_admin(_settings(enabled=False), logger) is None
    logger.warning.assert_not_called()
    logger.info.assert_not_called()


def test_enabled_builds_all_parts():
    logger = MagicMock()
    parts = di.build_firewall_admin(_settings(), logger)
    assert parts.fwctl.configured and parts.grafana.configured
    assert _warnings(logger) == []
    info = logger.info.call_args
    assert info.args[0] == "firewall_admin enabled"
    # 기동 로그에는 URL 만 남긴다
    assert set(info.kwargs) == {"fwctl_url", "grafana_url"}


def test_missing_tokens_still_builds_but_warns():
    logger = MagicMock()
    parts = di.build_firewall_admin(_settings(fwctl_token="", grafana_token=" "), logger)
    assert parts is not None
    assert parts.fwctl.configured is False and parts.grafana.configured is False
    warnings = _warnings(logger)
    assert len(warnings) == 2
    assert "fwctl not configured" in warnings[0] and "grafana not configured" in warnings[1]


async def test_status_reflects_configuration():
    parts = di.build_firewall_admin(_settings(grafana_token="", fwctl_url=""), MagicMock())
    status = await parts.control.status()
    assert status.fwctl_configured is False and status.health.reachable is False
    assert status.grafana_configured is False
    # URL 뒤 슬래시는 정리된다
    assert status.dashboard_url == "http://127.0.0.1:3000/d/fireware-firewall-lab"


def test_assembly_failure_returns_none_and_warns():
    logger = MagicMock()
    broken = SimpleNamespace(firewall_admin_enabled=True)  # 나머지 필드 없음
    assert di.build_firewall_admin(broken, logger) is None
    assert "assembly failed" in _warnings(logger)[0]


def _paths(app: FastAPI) -> set[str]:
    return set(app.openapi()["paths"])


def test_wire_disabled_registers_no_route(monkeypatch):
    """Plan SC-1 — 꺼져 있으면 404."""
    monkeypatch.setattr(di, "_parts", None)
    monkeypatch.setattr(di, "_built", True)
    app = FastAPI()
    assert di.wire_firewall_admin(app) is False
    assert not any(p.startswith("/api/v1/admin/firewall") for p in _paths(app))
    assert TestClient(app).get(STATUS).status_code == 404


def test_wire_enabled_registers_seven_routes(monkeypatch):
    parts = di.build_firewall_admin(_settings(fwctl_url=""), MagicMock())
    monkeypatch.setattr(di, "_parts", parts)
    monkeypatch.setattr(di, "_built", True)
    app = FastAPI()
    assert di.wire_firewall_admin(app) is True
    registered = {p for p in _paths(app) if p.startswith("/api/v1/admin/firewall")}
    assert registered == {
        "/api/v1/admin/firewall/status", "/api/v1/admin/firewall/blocks",
        "/api/v1/admin/firewall/blocks/{ip}", "/api/v1/admin/firewall/alerts",
        "/api/v1/admin/firewall/events", "/api/v1/admin/firewall/audit",
    }
    methods = app.openapi()["paths"]["/api/v1/admin/firewall/blocks"]
    assert set(methods) == {"get", "post"}

    admin = User(email="a@t", password_hash="h", role=UserRole.ADMIN,
                 status=UserStatus.APPROVED, id=1)
    app.dependency_overrides[get_current_user] = lambda: admin
    body = TestClient(app).get(STATUS).json()
    assert body["enabled"] is True and body["fwctl"]["configured"] is False


def test_get_builds_once(monkeypatch):
    calls = []

    def fake_build(settings, logger):
        calls.append(1)
        return None

    monkeypatch.setattr(di, "_parts", None)
    monkeypatch.setattr(di, "_built", False)
    monkeypatch.setattr(di, "build_firewall_admin", fake_build)
    assert di.get_firewall_admin() is None
    assert di.get_firewall_admin() is None
    assert calls == [1]


async def test_close_is_noop_when_not_built(monkeypatch):
    monkeypatch.setattr(di, "_parts", None)
    await di.close_firewall_admin()


async def test_close_closes_both_clients(monkeypatch):
    parts = di.build_firewall_admin(_settings(), MagicMock())
    monkeypatch.setattr(di, "_parts", parts)
    await di.close_firewall_admin()
    assert parts.fwctl._client.is_closed and parts.grafana._client.is_closed
