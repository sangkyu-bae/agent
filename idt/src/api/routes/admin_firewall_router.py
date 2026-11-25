"""Admin firewall router: /api/v1/admin/firewall/*.

Design Ref: firewall-admin-console §4, §6.1 — 라우터는 변환·오류 매핑만 한다.
권한은 라우터 수준에 걸어 엔드포인트별 누락이 생기지 않게 한다(§7).
이 라우터는 FIREWALL_ADMIN_ENABLED=true 일 때만 등록된다(firewall_admin_di).
"""
from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from src.application.firewall_admin.automation_service import (
    FirewallAutomationService,
)
from src.application.firewall_admin.control_service import (
    FirewallControlService,
    admin_request_id,
)
from src.application.firewall_admin.observability_service import (
    FirewallObservabilityService,
)
from src.domain.auth.entities import User
from src.domain.firewall_admin.errors import (
    FirewallAdminError,
    InvalidFilterError,
    InvalidIpError,
    InvalidReasonError,
    InvalidRequestError,
    InvalidTtlError,
)
from src.domain.firewall_admin.validation import MAX_TTL_SECONDS
from src.interfaces.dependencies.auth import get_current_user, require_role
from src.interfaces.schemas.firewall_admin import (
    AlertsResponse,
    AuditResponse,
    AutomationResponse,
    AutomationUpdateBody,
    BlockListResponse,
    BlockRequestBody,
    BlockResponse,
    EventsResponse,
    FirewallStatusResponse,
    UnblockResponse,
)


def _validation_error(exc: RequestValidationError) -> FirewallAdminError:
    """FastAPI 검증 오류(형이 틀린 입력) → 이 모듈의 오류 코드.

    Design Ref: firewall-admin-console §6.1 (Check G1) — 형이 틀린 값은 도메인 검증에
    닿기 전에 FastAPI 가 막는다. 그대로 두면 `{"detail": [...]}` 목록이 나가 화면이
    코드로 분기할 수 없으므로, 첫 오류의 위치로 같은 코드를 붙인다.
    """
    errors = exc.errors()
    loc = tuple(errors[0].get("loc", ())) if errors else ()
    source = loc[0] if loc else None
    field = str(loc[1]) if len(loc) > 1 else None
    details = {"field": field} if field else {}
    if source == "query":
        return InvalidFilterError(details=details)
    if source in ("body", "path") and field == "ip":
        return InvalidIpError(details=details)
    if source == "body" and field == "ttl_seconds":
        return InvalidTtlError(
            f"유지 시간은 1~{MAX_TTL_SECONDS}초입니다",
            details={**details, "max_ttl_seconds": MAX_TTL_SECONDS},
        )
    if source == "body" and field == "reason":
        return InvalidReasonError(details=details)
    # 본문이 JSON 이 아니거나, 받지 않는 필드(actor 등)를 보낸 경우
    return InvalidRequestError(details=details)


class _FirewallRoute(APIRoute):
    """이 라우터에만 검증 오류 변환을 건다(앱 전역 핸들러를 바꾸지 않는다)."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError as exc:
                error = _validation_error(exc)
                detail: dict = {"code": error.code, "message": str(error)}
                if error.details:
                    detail["details"] = error.details
                return JSONResponse(status_code=error.http_status, content={"detail": detail})

        return handler


router = APIRouter(
    prefix="/api/v1/admin/firewall",
    tags=["Admin Firewall"],
    dependencies=[Depends(require_role("admin"))],
    route_class=_FirewallRoute,
)


# ── DI 플레이스홀더 (firewall_admin_di.wire_firewall_admin 이 override) ──

def get_control_service() -> FirewallControlService:
    raise NotImplementedError


def get_observability_service() -> FirewallObservabilityService:
    raise NotImplementedError


def get_automation_service() -> FirewallAutomationService:
    """firewall-agent design §4.4 — 요청 세션 스코프로 조립된다(firewall_admin_di)."""
    raise NotImplementedError


def _http(error: FirewallAdminError, request_id: str | None = None) -> HTTPException:
    """오류가 소유한 code·status 를 그대로 옮긴다."""
    detail: dict = {"code": error.code, "message": str(error)}
    if request_id:
        detail["request_id"] = request_id
    if error.details:
        detail["details"] = error.details
    return HTTPException(status_code=error.http_status, detail=detail)


def _rid(user: User) -> str:
    return admin_request_id(str(user.id))


# ── 현황·집행 (fwctl) ──────────────────────────────────────────────

@router.get("/status", response_model=FirewallStatusResponse)
async def get_status(
    service: FirewallControlService = Depends(get_control_service),
):
    """항상 200. fwctl 장애는 reachable=false 로 알린다."""
    return FirewallStatusResponse.from_domain(await service.status())


@router.get("/blocks", response_model=BlockListResponse)
async def list_blocks(
    current_user: User = Depends(get_current_user),
    service: FirewallControlService = Depends(get_control_service),
):
    request_id = _rid(current_user)
    try:
        result = await service.list_blocks(request_id=request_id)
    except FirewallAdminError as e:
        raise _http(e, request_id) from e
    return BlockListResponse.from_domain(result)


@router.post("/blocks", status_code=201, response_model=BlockResponse)
async def block_ip(
    body: BlockRequestBody,
    current_user: User = Depends(get_current_user),
    service: FirewallControlService = Depends(get_control_service),
):
    request_id = _rid(current_user)
    try:
        result = await service.block(
            ip=body.ip, ttl_seconds=body.ttl_seconds, reason=body.reason,
            user_id=str(current_user.id), request_id=request_id,
        )
    except FirewallAdminError as e:
        raise _http(e, request_id) from e
    return BlockResponse.from_domain(result)


@router.delete("/blocks/{ip}", response_model=UnblockResponse)
async def unblock_ip(
    ip: str,
    current_user: User = Depends(get_current_user),
    service: FirewallControlService = Depends(get_control_service),
):
    request_id = _rid(current_user)
    try:
        result = await service.unblock(
            ip=ip, user_id=str(current_user.id), request_id=request_id
        )
    except FirewallAdminError as e:
        raise _http(e, request_id) from e
    return UnblockResponse.from_domain(result, request_id)


# ── 관측 (Grafana) ─────────────────────────────────────────────────

@router.get("/alerts", response_model=AlertsResponse)
async def get_alerts(
    service: FirewallObservabilityService = Depends(get_observability_service),
):
    try:
        return AlertsResponse.from_domain(await service.alerts())
    except FirewallAdminError as e:
        raise _http(e) from e


@router.get("/events", response_model=EventsResponse)
async def get_events(
    range: str | None = Query(None, description="15m|1h|6h|24h (기본 1h)"),
    action: str | None = Query(None, description="all|drop|block (기본 all)"),
    limit: int | None = Query(None, description="1~200 (기본 50)"),
    service: FirewallObservabilityService = Depends(get_observability_service),
):
    try:
        view = await service.events(range_=range, action=action, limit=limit)
    except FirewallAdminError as e:
        raise _http(e) from e
    return EventsResponse.from_domain(view)


@router.get("/audit", response_model=AuditResponse)
async def get_audit(
    range: str | None = Query(None, description="1h|6h|24h|7d (기본 24h)"),
    event: str | None = Query(None, description="all|block|unblock (기본 all)"),
    ip: str | None = Query(None),
    actor: str | None = Query(None, description="부분 일치"),
    limit: int | None = Query(None, description="1~200 (기본 100)"),
    service: FirewallObservabilityService = Depends(get_observability_service),
):
    try:
        view = await service.audit(
            range_=range, event=event, ip=ip, actor=actor, limit=limit
        )
    except FirewallAdminError as e:
        raise _http(e) from e
    return AuditResponse.from_domain(view)


# ── 자동 점검 (firewall-agent design §4.4) ─────────────────────────────

@router.get("/automation", response_model=AutomationResponse)
async def get_automation(
    service: FirewallAutomationService = Depends(get_automation_service),
):
    """보안 에이전트의 스케줄·알림 수신 상태. 미설정이어도 200 (configured=false)."""
    return AutomationResponse.from_domain(await service.state())


@router.put("/automation", response_model=AutomationResponse)
async def update_automation(
    body: AutomationUpdateBody,
    user: User = Depends(get_current_user),
    service: FirewallAutomationService = Depends(get_automation_service),
):
    """스케줄(전부)·알림 수신을 켜고 끈다. 보낸 항목만 바꾼다."""
    try:
        state = await service.update(
            schedule_enabled=body.schedule_enabled,
            alert_enabled=body.alert_enabled,
            admin_user_id=str(user.id),
        )
    except FirewallAdminError as e:
        raise _http(e) from e
    return AutomationResponse.from_domain(state)
