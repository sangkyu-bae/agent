"""firewall-admin-console module-1·2 — 입력 검증 (Design §4.2, §8.2 #1~4).

검증은 순수 함수다. I/O 없이 거부 판정만 확인한다.
"""
import pytest
from src.domain.firewall_admin.errors import (
    InvalidFilterError,
    InvalidIpError,
    InvalidReasonError,
    InvalidTtlError,
)
from src.domain.firewall_admin.validation import (
    normalize_ipv4,
    validate_audit_query,
    validate_block_request,
    validate_events_query,
)


class TestIp:
    def test_valid(self):
        assert normalize_ipv4("172.28.10.66") == "172.28.10.66"

    def test_strips_whitespace(self):
        assert normalize_ipv4(" 1.2.3.4 ") == "1.2.3.4"

    @pytest.mark.parametrize(
        "raw", ["1.2.3.0/24", "::1", "example.com", "", "   ", "1.2.3", "1.2.3.4.5", "01.2.3.4"]
    )
    def test_rejects_non_single_ipv4(self, raw):
        with pytest.raises(InvalidIpError):
            normalize_ipv4(raw)

    @pytest.mark.parametrize("raw", [None, 16909060, ["1.2.3.4"]])
    def test_rejects_non_string(self, raw):
        with pytest.raises(InvalidIpError):
            normalize_ipv4(raw)


class TestBlockRequest:
    def test_ok(self):
        req = validate_block_request(" 172.28.10.66 ", 600, "  포트 스캔  ")
        assert (req.ip, req.ttl_seconds, req.reason) == ("172.28.10.66", 600, "포트 스캔")

    def test_ttl_omitted_stays_none(self):
        assert validate_block_request("1.2.3.4", None, "r").ttl_seconds is None

    @pytest.mark.parametrize("ttl", [1, 3600])
    def test_ttl_bounds_ok(self, ttl):
        assert validate_block_request("1.2.3.4", ttl, "r").ttl_seconds == ttl

    @pytest.mark.parametrize("ttl", [0, -1, 3601, "600", True, 1.5])
    def test_ttl_rejected(self, ttl):
        with pytest.raises(InvalidTtlError) as e:
            validate_block_request("1.2.3.4", ttl, "r")
        assert e.value.details["max_ttl_seconds"] == 3600

    @pytest.mark.parametrize("reason", ["", "   ", None, "x" * 501, 123])
    def test_reason_rejected(self, reason):
        with pytest.raises(InvalidReasonError):
            validate_block_request("1.2.3.4", 60, reason)

    def test_reason_500_ok(self):
        assert len(validate_block_request("1.2.3.4", 60, "x" * 500).reason) == 500

    def test_ip_checked_first(self):
        with pytest.raises(InvalidIpError):
            validate_block_request("nope", 0, "")


class TestEventsQuery:
    def test_defaults(self):
        q = validate_events_query(None, None, None)
        assert (q.range, q.action, q.limit) == ("1h", "all", 50)

    @pytest.mark.parametrize("rng", ["15m", "1h", "6h", "24h"])
    def test_ranges(self, rng):
        assert validate_events_query(rng, "drop", 10).range == rng

    @pytest.mark.parametrize(
        "rng,action,limit",
        [("7d", "all", 10), ("1h", "accept", 10), ("1h", "all", 0), ("1h", "all", 201),
         ('1h"}', "all", 10), ("1h", 'drop"} | x', 10)],
    )
    def test_rejected(self, rng, action, limit):
        with pytest.raises(InvalidFilterError):
            validate_events_query(rng, action, limit)


class TestAuditQuery:
    def test_defaults(self):
        q = validate_audit_query(None, None, None, None, None)
        assert (q.range, q.event, q.ip, q.actor, q.limit) == ("24h", "all", None, None, 100)

    def test_full(self):
        q = validate_audit_query("7d", "block", " 1.2.3.4 ", "sangplusbot/admin:17", 20)
        assert (q.range, q.event, q.ip, q.actor) == ("7d", "block", "1.2.3.4", "sangplusbot/admin:17")

    def test_blank_filters_become_none(self):
        q = validate_audit_query("1h", "all", "  ", "", 10)
        assert q.ip is None and q.actor is None

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"range_": "8d"},
            {"range_": "15m"},
            {"event": "list"},
            {"event": "health"},
            {"actor": 'a"b'},
            {"actor": "a|b"},
            {"actor": "a{b}"},
            {"actor": "a\nb"},
            {"actor": "a`b"},
            {"actor": ".*"},
            {"actor": "x" * 101},
            {"ip": "1.2.3"},
            {"ip": '1.2.3.4" | line_format "x'},
            {"limit": 0},
            {"limit": 201},
        ],
    )
    def test_rejected(self, kwargs):
        base = {"range_": "24h", "event": "all", "ip": None, "actor": None, "limit": 100}
        base.update(kwargs)
        with pytest.raises(InvalidFilterError):
            validate_audit_query(
                base["range_"], base["event"], base["ip"], base["actor"], base["limit"]
            )
