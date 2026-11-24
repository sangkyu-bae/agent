"""firewall-admin-console 실측 — 실제 fwctl·Grafana 왕복 (Design §8.2 #22·#23).

가짜 응답만으로 완료 처리하지 않기 위한 테스트다. fireware 랩이 떠 있고
idt/.env 에 FIREWALL_ADMIN_* 가 설정돼 있어야 한다. 기본 실행에서는 건너뛴다.

실행:  FIREWALL_ADMIN_LIVE=1 python -m pytest tests/integration/test_firewall_admin_live.py -s

fwctl 이 dry-run 이 아니면 차단을 실제로 넣게 되므로 그 경우에는 중단한다
(대상은 랩의 attacker 주소이고 TTL 60초지만, 실측은 dry-run 에서만 한다).
"""
import asyncio
import os
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api import firewall_admin_di as di
from src.domain.auth.entities import User, UserRole, UserStatus
from src.infrastructure.logging import StructuredLogger
from src.interfaces.dependencies.auth import get_current_user

pytestmark = pytest.mark.skipif(
    os.environ.get("FIREWALL_ADMIN_LIVE") != "1",
    reason="실제 fwctl·Grafana 가 필요하다 (FIREWALL_ADMIN_LIVE=1)",
)

BASE = "/api/v1/admin/firewall"
ATTACKER = "172.28.10.66"   # 랩 attacker 컨테이너 주소 (화이트리스트 밖)
PROTECTED = "172.28.10.10"  # 랩 client — fwctl 화이트리스트
LIVE_USER_ID = 990017


@pytest.fixture(scope="module")
def client():
    from src.config import settings

    parts = di.build_firewall_admin(settings, StructuredLogger("firewall_admin.live"))
    assert parts is not None, "FIREWALL_ADMIN_ENABLED=true 가 아니다"
    assert parts.fwctl.configured and parts.grafana.configured, "URL·토큰 미설정"

    app = FastAPI()
    di._parts, di._built = parts, True
    assert di.wire_firewall_admin(app) is True
    admin = User(email="live@t", password_hash="h", role=UserRole.ADMIN,
                 status=UserStatus.APPROVED, id=LIVE_USER_ID)
    app.dependency_overrides[get_current_user] = lambda: admin
    with TestClient(app) as c:
        yield c
    asyncio.run(di.close_firewall_admin())
    di._parts, di._built = None, False


def test_status_is_reachable_and_dry_run(client):
    body = client.get(f"{BASE}/status").json()
    assert body["fwctl"]["reachable"] is True and body["fwctl"]["ipset_exists"] is True
    assert body["fwctl"]["dry_run"] is True, "실측은 dry-run 에서만 한다"
    assert body["grafana"]["configured"] is True


def test_block_list_unblock_roundtrip_and_audit_actor(client):
    """Plan SC-3·SC-4 — dry-run 왕복 후 fwctl 감사에 actor 가 남는다."""
    assert client.get(f"{BASE}/status").json()["fwctl"]["dry_run"] is True
    marker = f"live-{uuid.uuid4().hex[:8]}"

    blocked = client.post(f"{BASE}/blocks", json={
        "ip": ATTACKER, "ttl_seconds": 60, "reason": f"firewall-admin-console 실측 {marker}",
    })
    assert blocked.status_code == 201, blocked.text
    body = blocked.json()
    assert body["dry_run"] is True and body["ttl_seconds"] == 60
    block_rid = body["request_id"]
    assert block_rid.startswith(f"adm-{LIVE_USER_ID}-")

    listed = client.get(f"{BASE}/blocks")
    assert listed.status_code == 200 and listed.json()["dry_run"] is True
    # dry-run 이므로 실제 ipset 에는 들어가지 않는다
    assert ATTACKER not in [i["ip"] for i in listed.json()["items"]]

    unblocked = client.delete(f"{BASE}/blocks/{ATTACKER}")
    assert unblocked.status_code == 200, unblocked.text
    unblock_rid = unblocked.json()["request_id"]

    # Alloy → Loki 적재를 기다린다 (보통 수 초)
    actor = f"sangplusbot/admin:{LIVE_USER_ID}"
    found = {}
    for _ in range(20):
        r = client.get(f"{BASE}/audit", params={"range": "1h", "ip": ATTACKER, "limit": 50})
        assert r.status_code == 200, r.text
        found = {i["request_id"]: i for i in r.json()["items"]}
        if block_rid in found and unblock_rid in found:
            break
        import time

        time.sleep(1.5)
    assert block_rid in found, "차단 감사 행이 Loki 에 없다"
    row = found[block_rid]
    assert row["event"] == "block" and row["actor"] == actor
    assert row["dry_run"] is True and row["status"] == 201 and marker in row["reason"]
    # 해제는 fwctl 계약상 actor 가 없다 — 요청 ID 로 사용자를 찾는다
    assert unblock_rid in found and found[unblock_rid]["event"] == "unblock"
    assert unblock_rid.startswith(f"adm-{LIVE_USER_ID}-")

    # 수행자 필터
    by_actor = client.get(f"{BASE}/audit", params={"range": "1h", "actor": actor})
    assert block_rid in [i["request_id"] for i in by_actor.json()["items"]]


def test_whitelist_and_ttl_rejections(client):
    """Plan SC-5 — 안전장치가 그대로 전달된다."""
    protected = client.post(f"{BASE}/blocks", json={
        "ip": PROTECTED, "ttl_seconds": 60, "reason": "실측: 화이트리스트",
    })
    assert protected.status_code == 403, protected.text
    assert protected.json()["detail"]["code"] == "FORBIDDEN_WHITELIST"
    assert protected.json()["detail"]["details"]["matched"]

    too_long = client.post(f"{BASE}/blocks", json={
        "ip": ATTACKER, "ttl_seconds": 99999, "reason": "실측: TTL",
    })
    assert too_long.status_code == 422
    assert too_long.json()["detail"]["code"] == "INVALID_TTL"


def test_alerts_from_real_grafana(client):
    r = client.get(f"{BASE}/alerts")
    assert r.status_code == 200, r.text
    rules = r.json()["rules"]
    assert len(rules) == 8
    assert {x["rule_id"] for x in rules} == {"R01", "R02", "R03", "R04", "R06", "R07", "R08"}
    assert all(x["action_hint"] in {"block", "report", "extend"} for x in rules)


def test_events_from_real_loki(client):
    r = client.get(f"{BASE}/events", params={"range": "24h", "action": "all", "limit": 20})
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["top_sources"], list) and isinstance(body["recent"], list)
    for event in body["recent"]:
        assert event["action"] in {"drop", "block"}
        assert event["src_ip"] and event["dest_ip"]
