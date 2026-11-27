"""시장 분석 API L1 — 권한 · 형식 · 오류 코드 (design §5.1~5.3, §13.3, Plan SC-6).

런타임 서비스는 가짜로 바꾼다 — 라우터의 권한 의존성·본문 검증·오류 매핑만 본다.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.routes import market_analysis_router as ma_router
from src.application.market_analysis.access import GetAccessUseCase
from src.application.market_analysis.bootstrap_agents import (
    BootstrapItem,
    BootstrapStatus,
)
from src.application.market_analysis.commands import (
    InvalidSettingError,
    RoleAgentInvalidError,
    RoundBusyError,
)
from src.application.market_analysis.principles import (
    InvalidPriorityError,
    PrincipleNotFoundError,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.market_analysis.access import MANAGE_CODE, VIEW_CODE
from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.domain.market_analysis.value_objects import AgentRole, RoundKind
from src.interfaces.dependencies.auth import get_current_user

BASE = "/api/v1/market-analysis"
PAGE = {"items": [], "total": 0, "page": 1, "size": 20}
VIEW_GETS = [
    "/dashboard",
    "/positions",
    "/positions/1",
    "/decisions",
    "/reports",
    "/reports/1",
    "/insights",
    "/rounds",
    "/rounds/1",
    "/settings",
    "/role-agents",
]
SETTINGS_BODY = {
    "enabled": False,
    "round_times": ["10:00", "14:00", "18:10"],
    "max_per_round": 20,
    "max_per_day": 50,
    "max_concurrent_stocks": 2,
    "max_concurrent_runs": 4,
    "signal_rules": ["gap"],
    "ranking_kinds": ["volume"],
    "ranking_limit": 30,
    "slot_count": 10,
    "min_score_by_regime": {
        "strong_bull": 5,
        "bull": 6,
        "neutral": 6,
        "bear": 7,
        "strong_bear": 8,
    },
    "min_rr": 2.0,
    "max_stop_pct": 7.0,
    "min_stop_pct": 2.0,
    "max_principles": 10,
    "kis_server_id": "kis-1",
    "run_as_user_id": "7",
}
MANAGE_CALLS = [
    ("put", "/settings", SETTINGS_BODY),
    ("put", "/settings/enabled", {"enabled": True}),
    ("patch", "/principles/1", {"is_active": True}),
    ("put", "/role-agents", {"mapping": {"buy_judge": "a1"}}),
    ("post", "/bootstrap-agents", None),
    ("post", "/rounds/run-now", {"kind": "close"}),
]


class FakeCodes:
    def __init__(self, codes):
        self.codes = codes

    async def codes_for(self, user_id, role, request_id):
        return self.codes


def _api():
    queries = SimpleNamespace(
        dashboard=AsyncMock(return_value={"kpi": {}}),
        positions=AsyncMock(return_value=PAGE),
        position=AsyncMock(return_value={"id": 1}),
        decisions=AsyncMock(return_value=PAGE),
        reports=AsyncMock(return_value=PAGE),
        report=AsyncMock(return_value={"id": 1}),
        insights=AsyncMock(return_value={"principles": []}),
        rounds=AsyncMock(return_value=PAGE),
        round=AsyncMock(return_value={"id": 1}),
    )
    setting = MarketAnalysisSetting.defaults()
    return SimpleNamespace(
        queries=queries,
        settings=SimpleNamespace(get=AsyncMock(return_value=setting)),
        roles=SimpleNamespace(
            get_all=AsyncMock(return_value={AgentRole.BUY_JUDGE: "a1"})
        ),
        update_settings=SimpleNamespace(
            execute=AsyncMock(side_effect=lambda s, **k: s)
        ),
        set_enabled=SimpleNamespace(
            execute=AsyncMock(return_value=MarketAnalysisSetting(enabled=True))
        ),
        set_principle_active=SimpleNamespace(execute=AsyncMock(return_value=None)),
        set_role_agents=SimpleNamespace(
            execute=AsyncMock(return_value={AgentRole.BUY_JUDGE: "a1"})
        ),
        bootstrap=SimpleNamespace(
            execute=AsyncMock(
                return_value=[
                    BootstrapItem(AgentRole.SUMMARY, BootstrapStatus.CREATED, "s1")
                ]
            )
        ),
        run_now=SimpleNamespace(execute=AsyncMock(return_value=41)),
    )


def _client(codes=frozenset({VIEW_CODE, MANAGE_CODE}), api="default"):
    api = _api() if api == "default" else api
    app = FastAPI()
    app.include_router(ma_router.router)
    app.dependency_overrides[ma_router.get_access_use_case] = lambda: GetAccessUseCase(
        FakeCodes(codes), MagicMock()
    )
    app.dependency_overrides[ma_router.get_market_analysis_api] = lambda: api
    app.dependency_overrides[get_current_user] = lambda: User(
        email="x@t",
        password_hash="h",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=7,
    )
    return TestClient(app), api


def _call(client, method, path, body=None):
    fn = getattr(client, method)
    return fn(BASE + path, json=body) if body is not None else fn(BASE + path)


# ── 권한 (SC-6) ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", VIEW_GETS)
def test_view_routes_need_view(path):
    client, _ = _client(codes=frozenset())
    res = client.get(BASE + path)
    assert res.status_code == 403 and res.json()["detail"]["code"] == "MA_FORBIDDEN"
    viewer, _ = _client(codes=frozenset({VIEW_CODE}))
    assert viewer.get(BASE + path).status_code == 200


@pytest.mark.parametrize(("method", "path", "body"), MANAGE_CALLS)
def test_manage_routes_refuse_viewers(method, path, body):
    client, api = _client(codes=frozenset({VIEW_CODE}))
    res = _call(client, method, path, body)
    assert res.status_code == 403 and res.json()["detail"]["code"] == "MA_FORBIDDEN"


@pytest.mark.parametrize(("method", "path", "body"), MANAGE_CALLS)
def test_manage_routes_work_for_managers(method, path, body):
    client, _ = _client()
    assert _call(client, method, path, body).status_code in (200, 202)


# ── 형식 · 인자 ────────────────────────────────────────────────────────────


def test_query_args_are_passed_and_status_validated():
    client, api = _client()
    client.get(f"{BASE}/positions?status=closed&page=2&size=5")
    kw = api.queries.positions.call_args.kwargs
    assert (kw["status"], kw["page"], kw["size"]) == ("closed", 2, 5)
    assert client.get(f"{BASE}/positions?status=weird").status_code == 422
    client.get(f"{BASE}/reports?symbol=000660&date=2026-11-26")
    kw = api.queries.reports.call_args.kwargs
    assert (kw["symbol"], kw["trade_date"]) == ("000660", date(2026, 11, 26))
    client.get(f"{BASE}/decisions")
    kw = api.queries.decisions.call_args.kwargs
    assert (kw["kind"], kw["decision"]) == ("buy", "skip")  # 관심종목 기본


def test_settings_round_trip_and_role_agents_shape():
    client, api = _client()
    body = client.get(f"{BASE}/settings").json()
    assert body["round_times"] == ["10:00", "14:00", "18:10"] and body["min_rr"] == 2.0
    saved = client.put(f"{BASE}/settings", json=SETTINGS_BODY).json()
    assert saved["signal_rules"] == ["gap"] and saved["kis_server_id"] == "kis-1"
    passed = api.update_settings.execute.call_args.args[0]
    assert passed.round_times == ("10:00", "14:00", "18:10")
    assert api.update_settings.execute.call_args.kwargs["updated_by"] == "7"
    roles = client.get(f"{BASE}/role-agents").json()["roles"]
    assert len(roles) == len(AgentRole)
    buy = next(r for r in roles if r["role"] == "buy_judge")
    assert buy == {"role": "buy_judge", "name": "매수 판단", "agent_id": "a1"}


def test_run_now_and_bootstrap_shapes():
    client, api = _client()
    res = client.post(f"{BASE}/rounds/run-now", json={"kind": "intraday"})
    assert res.status_code == 202 and res.json() == {"round_id": 41}
    assert api.run_now.execute.call_args.args[0] is RoundKind.INTRADAY
    items = client.post(f"{BASE}/bootstrap-agents").json()["items"]
    assert items == [
        {"role": "summary", "status": "created", "agent_id": "s1", "error": None}
    ]
    assert api.bootstrap.execute.call_args.kwargs["owner_user_id"] == "7"


# ── 오류 코드 (§5.3) ───────────────────────────────────────────────────────


def test_not_found():
    api = _api()
    api.queries.position = AsyncMock(return_value=None)
    api.queries.report = AsyncMock(return_value=None)
    api.queries.round = AsyncMock(return_value=None)
    client, _ = _client(api=api)
    for path in ("/positions/9", "/reports/9", "/rounds/9"):
        res = client.get(BASE + path)
        assert res.status_code == 404 and res.json()["detail"]["code"] == "MA_NOT_FOUND"


def test_invalid_setting_lists_fields():
    api = _api()
    api.update_settings.execute = AsyncMock(
        side_effect=InvalidSettingError({"max_per_round": "1~200 사이여야 합니다"})
    )
    api.set_enabled.execute = AsyncMock(
        side_effect=InvalidSettingError({"kis_server_id": "필요"})
    )
    client, _ = _client(api=api)
    res = client.put(f"{BASE}/settings", json=SETTINGS_BODY)
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert (
        detail["code"] == "MA_INVALID_SETTING" and "max_per_round" in detail["errors"]
    )
    res = client.put(f"{BASE}/settings/enabled", json={"enabled": True})
    assert res.status_code == 422 and "kis_server_id" in res.json()["detail"]["errors"]


def test_role_agent_errors():
    api = _api()
    api.set_role_agents.execute = AsyncMock(
        side_effect=RoleAgentInvalidError(["sell_judge"])
    )
    client, _ = _client(api=api)
    res = client.put(f"{BASE}/role-agents", json={"mapping": {"sell_judge": "gone"}})
    assert res.status_code == 422
    assert res.json()["detail"] == {
        "code": "MA_ROLE_AGENT_INVALID",
        "message": "에이전트가 없거나 삭제되었습니다.",
        "roles": ["sell_judge"],
    }
    res = client.put(f"{BASE}/role-agents", json={"mapping": {"chef": "a1"}})
    assert res.status_code == 422 and res.json()["detail"]["roles"] == ["chef"]


def test_run_now_without_kind_lets_the_server_decide():
    client, api = _client()
    res = client.post(f"{BASE}/rounds/run-now", json={})
    assert res.status_code == 202
    assert api.run_now.execute.call_args.args[0] is None


def test_principle_errors_and_run_now_busy():
    api = _api()
    api.set_principle_active.execute = AsyncMock(side_effect=PrincipleNotFoundError(9))
    api.run_now.execute = AsyncMock(side_effect=RoundBusyError())
    client, _ = _client(api=api)
    res = client.patch(f"{BASE}/principles/9", json={"is_active": True})
    assert res.status_code == 404 and res.json()["detail"]["code"] == "MA_NOT_FOUND"
    res = client.post(f"{BASE}/rounds/run-now", json={"kind": "close"})
    assert res.status_code == 409 and res.json()["detail"]["code"] == "MA_ROUND_RUNNING"
    api.set_principle_active.execute = AsyncMock(side_effect=InvalidPriorityError("x"))
    res = client.patch(
        f"{BASE}/principles/1", json={"is_active": True, "priority": "x"}
    )
    assert res.status_code == 422


def test_runtime_unavailable_is_503():
    client, _ = _client(api=None)
    res = client.get(f"{BASE}/dashboard")
    assert res.status_code == 503 and res.json()["detail"]["code"] == "MA_UNAVAILABLE"
