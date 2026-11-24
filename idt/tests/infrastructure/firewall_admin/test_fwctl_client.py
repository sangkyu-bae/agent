"""firewall-admin-console module-1 — FwctlClient (Design §4.3, §6.1, §8.2 #7~9).

fwctl 은 httpx.MockTransport 로 흉내 낸다. 계약: fireware docs/fwctl-api.md v0.1.0.
"""
import json
from unittest.mock import MagicMock

import httpx
import pytest
from src.domain.firewall_admin.errors import (
    FirewallAdminError,
    ForbiddenWhitelistError,
    FwctlAuditError,
    FwctlAuthFailedError,
    FwctlTimeoutError,
    FwctlUnavailableError,
    InvalidIpError,
    InvalidTtlError,
)
from src.infrastructure.firewall_admin.fwctl_client import FwctlClient

TOKEN = "s3cret-token"


def _client(handler, token=TOKEN, logger=None) -> FwctlClient:
    return FwctlClient(
        base_url="http://fwctl.test",
        token=token,
        logger=logger or MagicMock(),
        transport=httpx.MockTransport(handler),
    )


def _err(status, code, details=None):
    return httpx.Response(
        status, json={"error": {"code": code, "message": "m", "details": details or {}},
                      "request_id": "rid"},
    )


BLOCK_OK = {
    "data": {
        "ip": "172.28.10.66", "ttl_seconds": 600,
        "expires_at": "2026-11-23T12:10:01.546Z", "reason": "scan",
        "actor": "sangplusbot/admin:7", "dry_run": True, "request_id": "rid-1",
    }
}


class TestBlock:
    async def test_sends_contract_request(self):
        seen = {}

        def handler(request: httpx.Request):
            seen["method"] = request.method
            seen["path"] = request.url.path
            seen["auth"] = request.headers["authorization"]
            seen["rid"] = request.headers["x-request-id"]
            seen["ctype"] = request.headers["content-type"]
            seen["body"] = json.loads(request.content)
            return httpx.Response(201, json=BLOCK_OK)

        result = await _client(handler).block(
            ip="172.28.10.66", ttl_seconds=600, reason="scan",
            actor="sangplusbot/admin:7", request_id="rid-1",
        )
        assert seen["method"] == "POST" and seen["path"] == "/v1/blocks"
        assert seen["auth"] == f"Bearer {TOKEN}"
        assert seen["rid"] == "rid-1"
        assert seen["ctype"].startswith("application/json")
        assert seen["body"] == {
            "ip": "172.28.10.66", "ttl_seconds": 600, "reason": "scan",
            "actor": "sangplusbot/admin:7",
        }
        assert result.dry_run is True and result.ttl_seconds == 600
        assert result.request_id == "rid-1"
        assert result.expires_at.isoformat() == "2026-11-23T12:10:01.546000+00:00"

    async def test_omits_ttl_when_none(self):
        seen = {}

        def handler(request):
            seen["body"] = json.loads(request.content)
            return httpx.Response(201, json=BLOCK_OK)

        await _client(handler).block(
            ip="1.2.3.4", ttl_seconds=None, reason="r", actor="a", request_id="x"
        )
        assert "ttl_seconds" not in seen["body"]

    @pytest.mark.parametrize(
        "response,expected",
        [
            (_err(400, "INVALID_IP"), InvalidIpError),
            (_err(400, "MISSING_FIELD", {"field": "actor"}), FwctlUnavailableError),
            (_err(400, "INVALID_JSON"), FwctlUnavailableError),
            (_err(401, "UNAUTHORIZED"), FwctlAuthFailedError),
            (_err(403, "FORBIDDEN_WHITELIST", {"matched": "172.28.10.10/32"}),
             ForbiddenWhitelistError),
            (_err(422, "INVALID_TTL", {"max_ttl_seconds": 3600}), InvalidTtlError),
            (_err(500, "AUDIT_ERROR"), FwctlAuditError),
            (_err(500, "IPSET_ERROR"), FwctlUnavailableError),
            (_err(500, "INTERNAL"), FwctlUnavailableError),
            (_err(503, "IPSET_MISSING"), FwctlUnavailableError),
            (httpx.Response(418, json={}), FwctlUnavailableError),
            (httpx.Response(201, text="not json"), FwctlUnavailableError),
            (httpx.Response(201, json={"data": {"ip": "1.2.3.4"}}), FwctlUnavailableError),
        ],
    )
    async def test_error_mapping(self, response, expected):
        with pytest.raises(expected):
            await _client(lambda r: response).block(
                ip="1.2.3.4", ttl_seconds=60, reason="r", actor="a", request_id="x"
            )

    async def test_whitelist_details_passed(self):
        resp = _err(403, "FORBIDDEN_WHITELIST", {"matched": "172.28.10.10/32"})
        with pytest.raises(ForbiddenWhitelistError) as e:
            await _client(lambda r: resp).block(
                ip="172.28.10.10", ttl_seconds=60, reason="r", actor="a", request_id="x"
            )
        assert e.value.details["matched"] == "172.28.10.10/32"

    async def test_ttl_details_passed(self):
        resp = _err(422, "INVALID_TTL", {"max_ttl_seconds": 1800})
        with pytest.raises(InvalidTtlError) as e:
            await _client(lambda r: resp).block(
                ip="1.2.3.4", ttl_seconds=3000, reason="r", actor="a", request_id="x"
            )
        assert e.value.details["max_ttl_seconds"] == 1800

    async def test_contract_drift_is_logged(self):
        logger = MagicMock()
        with pytest.raises(FwctlUnavailableError):
            await _client(lambda r: _err(400, "MISSING_FIELD"), logger=logger).block(
                ip="1.2.3.4", ttl_seconds=60, reason="r", actor="a", request_id="x"
            )
        assert "contract_drift" in logger.warning.call_args.args[0]

    async def test_timeout(self):
        def handler(request):
            raise httpx.ReadTimeout("slow", request=request)

        with pytest.raises(FwctlTimeoutError):
            await _client(handler).block(
                ip="1.2.3.4", ttl_seconds=60, reason="r", actor="a", request_id="x"
            )

    async def test_connect_error(self):
        def handler(request):
            raise httpx.ConnectError("refused", request=request)

        with pytest.raises(FwctlUnavailableError):
            await _client(handler).block(
                ip="1.2.3.4", ttl_seconds=60, reason="r", actor="a", request_id="x"
            )

    async def test_empty_token_sends_nothing(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(201, json=BLOCK_OK)

        client = _client(handler, token="")
        assert client.configured is False
        with pytest.raises(FwctlAuthFailedError):
            await client.block(
                ip="1.2.3.4", ttl_seconds=60, reason="r", actor="a", request_id="x"
            )
        with pytest.raises(FwctlAuthFailedError):
            await client.list_blocks(request_id="x")
        with pytest.raises(FwctlAuthFailedError):
            await client.unblock(ip="1.2.3.4", request_id="x")
        assert calls == []

    async def test_no_retry(self):
        calls = []

        def handler(request):
            calls.append(1)
            return _err(500, "IPSET_ERROR")

        with pytest.raises(FwctlUnavailableError):
            await _client(handler).block(
                ip="1.2.3.4", ttl_seconds=60, reason="r", actor="a", request_id="x"
            )
        assert len(calls) == 1

    async def test_token_never_in_error_text(self):
        with pytest.raises(FirewallAdminError) as e:
            await _client(lambda r: _err(401, "UNAUTHORIZED")).block(
                ip="1.2.3.4", ttl_seconds=60, reason="r", actor="a", request_id="x"
            )
        assert TOKEN not in str(e.value) and TOKEN not in json.dumps(e.value.details)


class TestList:
    async def test_ok(self):
        def handler(request):
            assert request.method == "GET" and request.url.path == "/v1/blocks"
            assert request.headers["x-request-id"] == "rid-2"
            return httpx.Response(200, json={
                "data": [{"ip": "172.28.10.66", "ttl_remaining_seconds": 583,
                          "packets": 12, "bytes": 720}],
                "dry_run": False, "ipset": "blocklist", "count": 1,
            })

        result = await _client(handler).list_blocks(request_id="rid-2")
        assert result.dry_run is False
        assert [(e.ip, e.ttl_remaining_seconds, e.packets, e.bytes) for e in result.items] == [
            ("172.28.10.66", 583, 12, 720)
        ]

    async def test_empty(self):
        resp = httpx.Response(200, json={"data": [], "dry_run": True, "count": 0})
        result = await _client(lambda r: resp).list_blocks(request_id="x")
        assert result.items == () and result.dry_run is True

    async def test_unauthorized(self):
        with pytest.raises(FwctlAuthFailedError):
            await _client(lambda r: _err(401, "UNAUTHORIZED")).list_blocks(request_id="x")


class TestUnblock:
    async def test_removed(self):
        def handler(request):
            assert request.method == "DELETE"
            assert request.url.path == "/v1/blocks/172.28.10.66"
            return httpx.Response(200, json={
                "data": {"ip": "172.28.10.66", "removed": True, "dry_run": False}
            })

        r = await _client(handler).unblock(ip="172.28.10.66", request_id="x")
        assert (r.removed, r.dry_run, r.already_absent) == (True, False, False)

    async def test_dry_run(self):
        resp = httpx.Response(200, json={
            "data": {"ip": "1.2.3.4", "removed": False, "dry_run": True}
        })
        r = await _client(lambda q: resp).unblock(ip="1.2.3.4", request_id="x")
        assert (r.removed, r.dry_run, r.already_absent) == (False, True, False)

    async def test_404_is_already_absent(self):
        r = await _client(lambda q: _err(404, "NOT_FOUND")).unblock(
            ip="1.2.3.4", request_id="x"
        )
        assert (r.removed, r.dry_run, r.already_absent) == (False, None, True)

    async def test_invalid_ip(self):
        with pytest.raises(InvalidIpError):
            await _client(lambda q: _err(400, "INVALID_IP")).unblock(
                ip="1.2.3.4", request_id="x"
            )


class TestHealth:
    async def test_ok_without_token_header(self):
        def handler(request):
            assert request.url.path == "/healthz"
            assert "authorization" not in request.headers
            return httpx.Response(200, json={
                "status": "ok", "dry_run": True, "ipset": "blocklist",
                "ipset_exists": True, "max_ttl_seconds": 3600, "version": "0.1.0",
            })

        h = await _client(handler).health()
        assert (h.reachable, h.dry_run, h.max_ttl_seconds, h.ipset_exists, h.version) == (
            True, True, 3600, True, "0.1.0"
        )

    async def test_degraded_503_is_reachable(self):
        resp = httpx.Response(503, json={
            "status": "degraded", "dry_run": True, "ipset": "blocklist",
            "ipset_exists": False, "max_ttl_seconds": 3600, "version": "0.1.0",
        })
        h = await _client(lambda r: resp).health()
        assert h.reachable is True and h.ipset_exists is False

    async def test_unreachable_never_raises(self):
        def handler(request):
            raise httpx.ConnectError("refused", request=request)

        logger = MagicMock()
        h = await _client(handler, logger=logger).health()
        assert h.reachable is False and h.dry_run is None
        # 상태 조회의 정상 결과라 warning 을 쌓지 않는다 (Check G5)
        logger.warning.assert_not_called()
        assert logger.debug.call_args.args[0] == "fwctl.health_unreachable"

    async def test_timeout_never_raises(self):
        def handler(request):
            raise httpx.ReadTimeout("slow", request=request)

        assert (await _client(handler).health()).reachable is False

    async def test_garbage_is_unreachable(self):
        h = await _client(lambda r: httpx.Response(200, text="<html>")).health()
        assert h.reachable is False

    async def test_works_without_token(self):
        resp = httpx.Response(200, json={
            "status": "ok", "dry_run": True, "ipset_exists": True,
            "max_ttl_seconds": 3600, "version": "0.1.0",
        })
        assert (await _client(lambda r: resp, token="").health()).reachable is True


async def test_aclose():
    client = _client(lambda r: httpx.Response(200, json={}))
    await client.aclose()
