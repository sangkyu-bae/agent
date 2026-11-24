"""firewall-admin-console module-1 — FirewallControlService (Design §2.2, §8.2 #14).

포트는 손으로 만든 가짜를 쓴다(AsyncMock 은 선언 안 된 메서드 호출을 못 잡는다).
"""
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from src.application.firewall_admin.control_service import (
    FirewallControlService,
    admin_actor,
    admin_request_id,
)
from src.domain.firewall_admin.errors import (
    ForbiddenWhitelistError,
    InvalidIpError,
    InvalidReasonError,
    InvalidTtlError,
)
from src.domain.firewall_admin.models import (
    BlockEntry,
    BlockList,
    BlockResult,
    FwctlHealth,
    UnblockResult,
)


class FakeFwctl:
    def __init__(self, *, configured=True, health=None, block_error=None):
        self.configured = configured
        self._health = health or FwctlHealth(
            reachable=True, dry_run=True, max_ttl_seconds=3600, ipset_exists=True,
            version="0.1.0",
        )
        self._block_error = block_error
        self.calls: list[tuple[str, dict]] = []

    async def health(self):
        self.calls.append(("health", {}))
        return self._health

    async def list_blocks(self, *, request_id):
        self.calls.append(("list", {"request_id": request_id}))
        return BlockList(items=(BlockEntry("172.28.10.66", 583, 12, 720),), dry_run=True)

    async def block(self, *, ip, ttl_seconds, reason, actor, request_id):
        self.calls.append(("block", {
            "ip": ip, "ttl_seconds": ttl_seconds, "reason": reason, "actor": actor,
            "request_id": request_id,
        }))
        if self._block_error:
            raise self._block_error
        return BlockResult(
            ip=ip, ttl_seconds=ttl_seconds or 600,
            expires_at=datetime(2026, 11, 23, 12, 10, tzinfo=UTC),
            reason=reason, dry_run=True, request_id=request_id,
        )

    async def unblock(self, *, ip, request_id):
        self.calls.append(("unblock", {"ip": ip, "request_id": request_id}))
        return UnblockResult(ip=ip, removed=False, dry_run=True, already_absent=False)


def _service(fwctl=None, **kwargs):
    logger = MagicMock()
    defaults = {"grafana_configured": True, "dashboard_url": "http://g/d/x"}
    defaults.update(kwargs)
    return FirewallControlService(fwctl or FakeFwctl(), logger=logger, **defaults), logger


def test_actor_and_request_id_format():
    assert admin_actor("17") == "sangplusbot/admin:17"
    rid = admin_request_id("17")
    # fwctl X-Request-Id 허용 형식: [A-Za-z0-9._:-]{1,64}
    assert rid.startswith("adm-17-") and len(rid) <= 64
    assert all(c.isalnum() or c in "._:-" for c in rid)
    assert admin_request_id("17") != rid


class TestBlock:
    async def test_actor_is_server_generated(self):
        fwctl = FakeFwctl()
        service, _ = _service(fwctl)
        result = await service.block(
            ip=" 172.28.10.66 ", ttl_seconds=600, reason=" scan ", user_id="17",
            request_id="adm-17-abc",
        )
        assert fwctl.calls == [("block", {
            "ip": "172.28.10.66", "ttl_seconds": 600, "reason": "scan",
            "actor": "sangplusbot/admin:17", "request_id": "adm-17-abc",
        })]
        assert result.dry_run is True

    @pytest.mark.parametrize(
        "kwargs,error",
        [
            ({"ip": "1.2.3.0/24"}, InvalidIpError),
            ({"ttl_seconds": 99999}, InvalidTtlError),
            ({"reason": "  "}, InvalidReasonError),
        ],
    )
    async def test_invalid_input_never_reaches_fwctl(self, kwargs, error):
        fwctl = FakeFwctl()
        service, _ = _service(fwctl)
        args = {"ip": "1.2.3.4", "ttl_seconds": 60, "reason": "r"}
        args.update(kwargs)
        with pytest.raises(error):
            await service.block(**args, user_id="17", request_id="x")
        assert fwctl.calls == []

    async def test_logs_user_without_token(self):
        service, logger = _service()
        await service.block(
            ip="1.2.3.4", ttl_seconds=60, reason="r", user_id="17", request_id="rid"
        )
        message, kwargs = logger.info.call_args.args[0], logger.info.call_args.kwargs
        assert message == "firewall_admin.block"
        assert kwargs["user_id"] == "17" and kwargs["ip"] == "1.2.3.4"
        assert kwargs["dry_run"] is True and kwargs["request_id"] == "rid"
        assert not any("token" in k for k in kwargs)

    async def test_fwctl_rejection_is_logged_and_raised(self):
        service, logger = _service(FakeFwctl(block_error=ForbiddenWhitelistError()))
        with pytest.raises(ForbiddenWhitelistError):
            await service.block(
                ip="172.28.10.10", ttl_seconds=60, reason="r", user_id="17", request_id="rid"
            )
        kwargs = logger.warning.call_args.kwargs
        assert logger.warning.call_args.args[0] == "firewall_admin.block_rejected"
        assert kwargs["code"] == "FORBIDDEN_WHITELIST" and kwargs["user_id"] == "17"


class TestUnblock:
    async def test_normalizes_ip_and_logs(self):
        fwctl = FakeFwctl()
        service, logger = _service(fwctl)
        result = await service.unblock(ip=" 172.28.10.66 ", user_id="17", request_id="rid")
        assert fwctl.calls == [("unblock", {"ip": "172.28.10.66", "request_id": "rid"})]
        assert result.ip == "172.28.10.66"
        assert logger.info.call_args.args[0] == "firewall_admin.unblock"
        assert logger.info.call_args.kwargs["user_id"] == "17"

    async def test_invalid_ip(self):
        fwctl = FakeFwctl()
        service, _ = _service(fwctl)
        with pytest.raises(InvalidIpError):
            await service.unblock(ip="../healthz", user_id="17", request_id="x")
        assert fwctl.calls == []


async def test_list_blocks():
    service, _ = _service()
    result = await service.list_blocks(request_id="rid")
    assert result.items[0].ip == "172.28.10.66"


class TestStatus:
    async def test_ok(self):
        service, _ = _service()
        s = await service.status()
        assert s.fwctl_configured is True and s.health.reachable is True
        assert s.grafana_configured is True and s.dashboard_url == "http://g/d/x"
        assert s.default_ttl_seconds == 600

    async def test_default_ttl_capped_by_max(self):
        health = FwctlHealth(reachable=True, dry_run=True, max_ttl_seconds=300,
                             ipset_exists=True, version="0.1.0")
        service, _ = _service(FakeFwctl(health=health))
        assert (await service.status()).default_ttl_seconds == 300

    async def test_unreachable(self):
        service, _ = _service(FakeFwctl(health=FwctlHealth(reachable=False)))
        s = await service.status()
        assert s.health.reachable is False and s.default_ttl_seconds == 600

    async def test_not_configured(self):
        service, _ = _service(FakeFwctl(configured=False), grafana_configured=False,
                              dashboard_url=None)
        s = await service.status()
        assert s.fwctl_configured is False
        assert s.grafana_configured is False and s.dashboard_url is None
