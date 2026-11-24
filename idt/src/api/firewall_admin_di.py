"""firewall-admin-console 조립 — 코어에 끼우는 단일 지점.

Design Ref: firewall-admin-console §6.3, §9.2 — source_viewer_di 선례. main.py 는
wire_firewall_admin(app) 과 close_firewall_admin() 두 개만 부른다. firewall_admin
패키지를 import 하는 곳은 여기와 라우터·스키마뿐이다(tests/contracts 로 고정).

- FIREWALL_ADMIN_ENABLED=false(기본) → 조립하지 않음, 라우터 미등록(404)
- 켰는데 URL·토큰이 비어 있음 → 라우터는 등록, warning 1회, status 가 configured=false
- 조립 실패 → warning 1회 후 기능 없음. 앱 기동은 계속된다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI

from src.api.routes import admin_firewall_router
from src.application.firewall_admin.control_service import FirewallControlService
from src.application.firewall_admin.observability_service import (
    FirewallObservabilityService,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.firewall_admin.fwctl_client import FwctlClient
from src.infrastructure.firewall_admin.grafana_client import GrafanaClient
from src.infrastructure.logging import StructuredLogger

# fireware observability/grafana/provisioning/dashboards/firewall-lab.json 의 uid
DASHBOARD_PATH = "/d/fireware-firewall-lab"


@dataclass(frozen=True)
class FirewallAdminParts:
    control: FirewallControlService
    observability: FirewallObservabilityService
    fwctl: FwctlClient
    grafana: GrafanaClient


_parts: FirewallAdminParts | None = None
_built = False


def build_firewall_admin(settings: Any, logger: LoggerInterface) -> FirewallAdminParts | None:
    """설정 → 부품. 소비: config.firewall_admin_* 5개."""
    if not settings.firewall_admin_enabled:
        return None
    try:
        fwctl_url = (settings.firewall_admin_fwctl_url or "").strip().rstrip("/")
        grafana_url = (settings.firewall_admin_grafana_url or "").strip().rstrip("/")
        fwctl = FwctlClient(
            base_url=fwctl_url, token=settings.firewall_admin_fwctl_token, logger=logger
        )
        grafana = GrafanaClient(
            base_url=grafana_url, token=settings.firewall_admin_grafana_token, logger=logger
        )
        # 조용히 꺼지지 않게: 켰는데 비어 있으면 기동 로그에 남긴다(토큰 값은 기록하지 않는다).
        if not fwctl.configured:
            logger.warning("firewall_admin: fwctl not configured — block/unblock will fail")
        if not grafana.configured:
            logger.warning("firewall_admin: grafana not configured — alerts/events/audit off")
        logger.info("firewall_admin enabled", fwctl_url=fwctl_url, grafana_url=grafana_url)
        return FirewallAdminParts(
            control=FirewallControlService(
                fwctl,
                grafana_configured=grafana.configured,
                dashboard_url=f"{grafana_url}{DASHBOARD_PATH}" if grafana_url else None,
                logger=logger,
            ),
            observability=FirewallObservabilityService(grafana, logger=logger),
            fwctl=fwctl,
            grafana=grafana,
        )
    except Exception as e:  # noqa: BLE001 — 부가 기능 조립 실패가 기동을 막으면 안 된다
        logger.warning("firewall_admin assembly failed — feature disabled", exception=e)
        return None


def get_firewall_admin() -> FirewallAdminParts | None:
    """앱 수명 1회 조립 — 요청마다 재시도하지 않는다."""
    global _parts, _built
    if not _built:
        from src.config import settings

        _built = True
        _parts = build_firewall_admin(settings, StructuredLogger("firewall_admin"))
    return _parts


def wire_firewall_admin(app: FastAPI) -> bool:
    """관리자 방화벽 라우터 등록. 꺼져 있으면 등록하지 않는다(전 경로 404)."""
    parts = get_firewall_admin()
    if parts is None:
        return False
    app.dependency_overrides[admin_firewall_router.get_control_service] = (
        lambda: parts.control
    )
    app.dependency_overrides[admin_firewall_router.get_observability_service] = (
        lambda: parts.observability
    )
    app.include_router(admin_firewall_router.router)
    return True


async def close_firewall_admin() -> None:
    """HTTP 클라이언트 정리 (best-effort, 조립 안 했으면 no-op)."""
    if _parts is None:
        return
    for client in (_parts.fwctl, _parts.grafana):
        try:
            await client.aclose()
        except Exception:  # noqa: BLE001 — 종료 경로
            pass
