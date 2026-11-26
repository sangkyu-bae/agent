"""시장 분석 라우터: /api/v1/market-analysis/*.

Design Ref: stock-analysis-agents §5.1, §5.3, DD10. MARKET_ANALYSIS_ENABLED=true 일 때만
등록된다(market_analysis_di). 다른 경로는
require_view / require_manage 를 의존성으로 건다.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.application.market_analysis.access import (
    GetAccessUseCase,
    MarketAnalysisForbiddenError,
)
from src.application.market_analysis.commands import (
    InvalidSettingError,
    RoleAgentInvalidError,
    RoundBusyError,
)
from src.application.market_analysis.default_prompts import ROLE_NAMES
from src.application.market_analysis.principles import (
    InvalidPriorityError,
    PrincipleNotFoundError,
)
from src.domain.auth.entities import User
from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.domain.market_analysis.value_objects import AgentRole, RoundKind
from src.interfaces.dependencies.auth import get_current_user

router = APIRouter(prefix="/api/v1/market-analysis", tags=["market-analysis"])


class AccessResponse(BaseModel):
    enabled: bool
    can_view: bool
    can_manage: bool


def get_access_use_case() -> GetAccessUseCase:
    """market_analysis_di 가 요청 세션 스코프 팩토리로 덮어쓴다."""
    raise NotImplementedError("market_analysis is not wired")


def _forbidden() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": "MA_FORBIDDEN", "message": "시장 분석 권한이 없습니다."},
    )


async def _require(level: str, user: User, uc: GetAccessUseCase) -> User:
    try:
        await uc.require(
            user_id=int(user.id),
            role=user.role.value,
            level=level,
            request_id=str(uuid.uuid4()),
        )
    except MarketAnalysisForbiddenError:
        raise _forbidden() from None
    return user


async def require_view(
    current_user: User = Depends(get_current_user),
    uc: GetAccessUseCase = Depends(get_access_use_case),
) -> User:
    return await _require("view", current_user, uc)


async def require_manage(
    current_user: User = Depends(get_current_user),
    uc: GetAccessUseCase = Depends(get_access_use_case),
) -> User:
    return await _require("manage", current_user, uc)


@router.get("/access", response_model=AccessResponse)
async def get_access(
    current_user: User = Depends(get_current_user),
    uc: GetAccessUseCase = Depends(get_access_use_case),
) -> AccessResponse:
    """메뉴 노출 판단 — 권한이 없어도 200 으로 can_view=false 를 돌려준다."""
    decision = await uc.execute(
        user_id=int(current_user.id),
        role=current_user.role.value,
        request_id=str(uuid.uuid4()),
    )
    return AccessResponse(
        enabled=decision.enabled,
        can_view=decision.can_view,
        can_manage=decision.can_manage,
    )


# ── module-8: 조회 · 설정 · 운영 (Design §5.1~5.3) ──────────────────────────────
# 조회 응답 형태는 application.queries / infrastructure.query_repository 가 정한다
# (테스트로 고정). 프론트 타입은 module-9 에서 같은 형태로 만든다.


def get_market_analysis_api() -> Any:
    """market_analysis_di 가 런타임 서비스 묶음으로 덮어쓴다."""
    raise NotImplementedError("market_analysis is not wired")


def _rid() -> str:
    return str(uuid.uuid4())


def _error(status_code: int, code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message, **extra}
    )


def _api(api: Any) -> Any:
    if api is None:
        raise _error(503, "MA_UNAVAILABLE", "시장 분석 실행기를 준비하지 못했습니다.")
    return api


def _not_found(what: str) -> HTTPException:
    return _error(404, "MA_NOT_FOUND", f"{what}을(를) 찾을 수 없습니다.")


def _found(value: dict[str, Any] | None, what: str) -> dict[str, Any]:
    if value is None:
        raise _not_found(what)
    return value


class SettingsBody(BaseModel):
    enabled: bool = False
    round_times: list[str]
    max_per_round: int
    max_per_day: int
    max_concurrent_stocks: int
    max_concurrent_runs: int
    signal_rules: list[str]
    rule_params: dict[str, Any] | None = None
    ranking_kinds: list[str]
    ranking_limit: int
    condition_seqs: list[str] = Field(default_factory=list)
    intraday_entry_allowed: bool = True
    slot_count: int
    min_score_by_regime: dict[str, int]
    min_rr: Decimal
    max_stop_pct: Decimal
    min_stop_pct: Decimal
    max_principles: int
    principle_auto_activate: bool = False
    run_as_user_id: str | None = None
    kis_server_id: str | None = None
    dart_server_id: str | None = None
    perplexity_server_id: str | None = None

    def to_setting(self) -> MarketAnalysisSetting:
        return MarketAnalysisSetting(
            enabled=self.enabled,
            round_times=tuple(self.round_times),
            max_per_round=self.max_per_round,
            max_per_day=self.max_per_day,
            max_concurrent_stocks=self.max_concurrent_stocks,
            max_concurrent_runs=self.max_concurrent_runs,
            signal_rules=tuple(self.signal_rules),
            rule_params=self.rule_params,
            ranking_kinds=tuple(self.ranking_kinds),
            ranking_limit=self.ranking_limit,
            condition_seqs=tuple(self.condition_seqs),
            intraday_entry_allowed=self.intraday_entry_allowed,
            slot_count=self.slot_count,
            min_score_by_regime=dict(self.min_score_by_regime),
            min_rr=self.min_rr,
            max_stop_pct=self.max_stop_pct,
            min_stop_pct=self.min_stop_pct,
            max_principles=self.max_principles,
            principle_auto_activate=self.principle_auto_activate,
            run_as_user_id=self.run_as_user_id or None,
            kis_server_id=self.kis_server_id or None,
            dart_server_id=self.dart_server_id or None,
            perplexity_server_id=self.perplexity_server_id or None,
        )


def _settings_out(s: MarketAnalysisSetting) -> dict[str, Any]:
    return {
        "enabled": s.enabled,
        "round_times": list(s.round_times),
        "max_per_round": s.max_per_round,
        "max_per_day": s.max_per_day,
        "max_concurrent_stocks": s.max_concurrent_stocks,
        "max_concurrent_runs": s.max_concurrent_runs,
        "signal_rules": list(s.signal_rules),
        "rule_params": s.rule_params,
        "ranking_kinds": list(s.ranking_kinds),
        "ranking_limit": s.ranking_limit,
        "condition_seqs": list(s.condition_seqs),
        "intraday_entry_allowed": s.intraday_entry_allowed,
        "slot_count": s.slot_count,
        "min_score_by_regime": dict(s.min_score_by_regime),
        "min_rr": float(s.min_rr),
        "max_stop_pct": float(s.max_stop_pct),
        "min_stop_pct": float(s.min_stop_pct),
        "max_principles": s.max_principles,
        "principle_auto_activate": s.principle_auto_activate,
        "run_as_user_id": s.run_as_user_id,
        "kis_server_id": s.kis_server_id,
        "dart_server_id": s.dart_server_id,
        "perplexity_server_id": s.perplexity_server_id,
    }


class EnabledBody(BaseModel):
    enabled: bool


class PrincipleBody(BaseModel):
    is_active: bool
    priority: str | None = None


class RoleAgentsBody(BaseModel):
    mapping: dict[str, str]


class RunNowBody(BaseModel):
    kind: RoundKind = RoundKind.CLOSE


def _invalid_setting(e: InvalidSettingError) -> HTTPException:
    return _error(422, "MA_INVALID_SETTING", "설정 값을 확인하세요.", errors=e.errors)


# ── 조회 (view) ────────────────────────────────────────────────────────────


@router.get("/dashboard")
async def get_dashboard(
    _user: User = Depends(require_view), api: Any = Depends(get_market_analysis_api)
) -> dict[str, Any]:
    return await _api(api).queries.dashboard(_rid())


@router.get("/positions")
async def list_positions(
    status_: Literal["open", "closed"] = Query("open", alias="status"),
    page: int = 1,
    size: int = 20,
    _user: User = Depends(require_view),
    api: Any = Depends(get_market_analysis_api),
) -> dict[str, Any]:
    return await _api(api).queries.positions(
        status=status_, page=page, size=size, request_id=_rid()
    )


@router.get("/positions/{position_id}")
async def get_position(
    position_id: int,
    _user: User = Depends(require_view),
    api: Any = Depends(get_market_analysis_api),
) -> dict[str, Any]:
    return _found(await _api(api).queries.position(position_id, _rid()), "포지션")


@router.get("/decisions")
async def list_decisions(
    kind: Literal["buy", "sell"] = "buy",
    decision: str | None = "skip",
    page: int = 1,
    size: int = 20,
    _user: User = Depends(require_view),
    api: Any = Depends(get_market_analysis_api),
) -> dict[str, Any]:
    return await _api(api).queries.decisions(
        kind=kind, decision=decision or None, page=page, size=size, request_id=_rid()
    )


@router.get("/reports")
async def list_reports(
    symbol: str | None = None,
    trade_date: date | None = Query(None, alias="date"),
    page: int = 1,
    size: int = 20,
    _user: User = Depends(require_view),
    api: Any = Depends(get_market_analysis_api),
) -> dict[str, Any]:
    return await _api(api).queries.reports(
        symbol=symbol, trade_date=trade_date, page=page, size=size, request_id=_rid()
    )


@router.get("/reports/{report_id}")
async def get_report(
    report_id: int,
    _user: User = Depends(require_view),
    api: Any = Depends(get_market_analysis_api),
) -> dict[str, Any]:
    return _found(await _api(api).queries.report(report_id, _rid()), "리포트")


@router.get("/insights")
async def get_insights(
    _user: User = Depends(require_view), api: Any = Depends(get_market_analysis_api)
) -> dict[str, Any]:
    return await _api(api).queries.insights(_rid())


@router.get("/rounds")
async def list_rounds(
    page: int = 1,
    size: int = 20,
    _user: User = Depends(require_view),
    api: Any = Depends(get_market_analysis_api),
) -> dict[str, Any]:
    return await _api(api).queries.rounds(page=page, size=size, request_id=_rid())


@router.get("/rounds/{round_id}")
async def get_round(
    round_id: int,
    _user: User = Depends(require_view),
    api: Any = Depends(get_market_analysis_api),
) -> dict[str, Any]:
    return _found(await _api(api).queries.round(round_id, _rid()), "회차")


@router.get("/settings")
async def get_settings(
    _user: User = Depends(require_view), api: Any = Depends(get_market_analysis_api)
) -> dict[str, Any]:
    return _settings_out(await _api(api).settings.get(_rid()))


@router.get("/role-agents")
async def get_role_agents(
    _user: User = Depends(require_view), api: Any = Depends(get_market_analysis_api)
) -> dict[str, Any]:
    mapping = await _api(api).roles.get_all(_rid())
    return {
        "roles": [
            {
                "role": role.value,
                "name": ROLE_NAMES[role],
                "agent_id": mapping.get(role),
            }
            for role in AgentRole
        ]
    }


# ── 변경 (manage) ──────────────────────────────────────────────────────────


@router.put("/settings")
async def put_settings(
    body: SettingsBody,
    user: User = Depends(require_manage),
    api: Any = Depends(get_market_analysis_api),
) -> dict[str, Any]:
    try:
        saved = await _api(api).update_settings.execute(
            body.to_setting(), updated_by=str(user.id), request_id=_rid()
        )
    except InvalidSettingError as e:
        raise _invalid_setting(e) from None
    return _settings_out(saved)


@router.put("/settings/enabled")
async def put_enabled(
    body: EnabledBody,
    user: User = Depends(require_manage),
    api: Any = Depends(get_market_analysis_api),
) -> dict[str, Any]:
    try:
        saved = await _api(api).set_enabled.execute(
            body.enabled, updated_by=str(user.id), request_id=_rid()
        )
    except InvalidSettingError as e:
        raise _invalid_setting(e) from None
    return {"enabled": saved.enabled}


@router.patch("/principles/{principle_id}")
async def patch_principle(
    principle_id: int,
    body: PrincipleBody,
    user: User = Depends(require_manage),
    api: Any = Depends(get_market_analysis_api),
) -> dict[str, Any]:
    try:
        await _api(api).set_principle_active.execute(
            principle_id=principle_id,
            is_active=body.is_active,
            priority=body.priority,
            updated_by=str(user.id),
            request_id=_rid(),
        )
    except PrincipleNotFoundError:
        raise _not_found("원칙") from None
    except InvalidPriorityError:
        raise _error(
            422,
            "MA_INVALID_SETTING",
            "우선순위는 high·medium·low 중 하나입니다.",
            errors={"priority": "high·medium·low 중 하나"},
        ) from None
    return {"id": principle_id, "is_active": body.is_active, "priority": body.priority}


@router.put("/role-agents")
async def put_role_agents(
    body: RoleAgentsBody,
    user: User = Depends(require_manage),
    api: Any = Depends(get_market_analysis_api),
) -> dict[str, Any]:
    known = {role.value: role for role in AgentRole}
    unknown = sorted(k for k in body.mapping if k not in known)
    if unknown:
        raise _error(422, "MA_ROLE_AGENT_INVALID", "모르는 역할입니다.", roles=unknown)
    try:
        mapping = await _api(api).set_role_agents.execute(
            {known[k]: v for k, v in body.mapping.items()},
            updated_by=str(user.id),
            request_id=_rid(),
        )
    except RoleAgentInvalidError as e:
        raise _error(
            422,
            "MA_ROLE_AGENT_INVALID",
            "에이전트가 없거나 삭제되었습니다.",
            roles=e.roles,
        ) from None
    return {"mapping": {role.value: agent for role, agent in mapping.items()}}


@router.post("/bootstrap-agents")
async def post_bootstrap(
    user: User = Depends(require_manage), api: Any = Depends(get_market_analysis_api)
) -> dict[str, Any]:
    items = await _api(api).bootstrap.execute(
        owner_user_id=str(user.id), request_id=_rid()
    )
    return {
        "items": [
            {
                "role": i.role.value,
                "status": i.status.value,
                "agent_id": i.agent_id,
                "error": i.error,
            }
            for i in items
        ]
    }


@router.post("/rounds/run-now", status_code=status.HTTP_202_ACCEPTED)
async def post_run_now(
    body: RunNowBody,
    user: User = Depends(require_manage),
    api: Any = Depends(get_market_analysis_api),
) -> dict[str, Any]:
    try:
        round_id = await _api(api).run_now.execute(
            body.kind, requested_by=str(user.id), request_id=_rid()
        )
    except RoundBusyError:
        raise _error(
            409,
            "MA_ROUND_RUNNING",
            "실행 중인 회차가 있습니다. 끝난 뒤 다시 시도하세요.",
        ) from None
    return {"round_id": round_id}
