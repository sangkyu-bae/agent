"""현황 조회·수동 차단·해제.

Design Ref: firewall-admin-console §2.2, §4.3 — idt 는 형식만 검증하고 fwctl 로
넘긴다. actor 는 서버가 만든다(클라이언트 입력을 받지 않는다).
Plan SC-4: fwctl 감사에 sangplusbot/admin:<user_id> 가 남아야 한다.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from src.application.firewall_admin.ports import FwctlPort
from src.domain.firewall_admin.errors import FirewallAdminError
from src.domain.firewall_admin.models import (
    BlockList,
    BlockResult,
    FwctlHealth,
    UnblockResult,
)
from src.domain.firewall_admin.validation import normalize_ipv4, validate_block_request
from src.domain.logging.interfaces.logger_interface import LoggerInterface

ACTOR_PREFIX = "sangplusbot/admin:"
DEFAULT_TTL_SECONDS = 600  # fwctl FWCTL_DEFAULT_TTL 기본값과 같다 (폼 초기값)


def admin_actor(user_id: str) -> str:
    return f"{ACTOR_PREFIX}{user_id}"


def admin_request_id(user_id: str) -> str:
    """fwctl 감사에 남는 요청 ID. `adm-<user_id>-<난수>`.

    fwctl 의 DELETE 는 본문이 없어 actor 가 감사에 남지 않는다. 해제한 사용자를
    감사에서 찾을 수 있도록 요청 ID 에 사용자 ID 를 싣는다.
    형식은 fwctl 허용 범위([A-Za-z0-9._:-]{1,64}) 안이다.
    """
    return f"adm-{user_id}-{uuid.uuid4().hex[:24]}"[:64]


@dataclass(frozen=True)
class FirewallStatus:
    fwctl_configured: bool
    health: FwctlHealth
    grafana_configured: bool
    dashboard_url: str | None
    default_ttl_seconds: int


class FirewallControlService:
    def __init__(
        self,
        fwctl: FwctlPort,
        *,
        grafana_configured: bool,
        dashboard_url: str | None,
        logger: LoggerInterface,
    ) -> None:
        self._fwctl = fwctl
        self._grafana_configured = grafana_configured
        self._dashboard_url = dashboard_url
        self._logger = logger

    async def status(self) -> FirewallStatus:
        health = await self._fwctl.health()
        default_ttl = DEFAULT_TTL_SECONDS
        if health.max_ttl_seconds:
            default_ttl = min(default_ttl, health.max_ttl_seconds)
        return FirewallStatus(
            fwctl_configured=self._fwctl.configured,
            health=health,
            grafana_configured=self._grafana_configured,
            dashboard_url=self._dashboard_url,
            default_ttl_seconds=default_ttl,
        )

    async def list_blocks(self, *, request_id: str) -> BlockList:
        return await self._fwctl.list_blocks(request_id=request_id)

    async def block(
        self, *, ip: object, ttl_seconds: object, reason: object, user_id: str, request_id: str
    ) -> BlockResult:
        request = validate_block_request(ip, ttl_seconds, reason)
        try:
            result = await self._fwctl.block(
                ip=request.ip, ttl_seconds=request.ttl_seconds, reason=request.reason,
                actor=admin_actor(user_id), request_id=request_id,
            )
        except FirewallAdminError as e:
            self._logger.warning(
                "firewall_admin.block_rejected", user_id=user_id, ip=request.ip,
                code=e.code, request_id=request_id,
            )
            raise
        self._logger.info(
            "firewall_admin.block", user_id=user_id, ip=result.ip,
            ttl_seconds=result.ttl_seconds, dry_run=result.dry_run, request_id=request_id,
        )
        return result

    async def unblock(self, *, ip: object, user_id: str, request_id: str) -> UnblockResult:
        # 경로에 들어가는 값이므로 IPv4 정규화 결과만 쓴다.
        normalized = normalize_ipv4(ip)
        try:
            result = await self._fwctl.unblock(ip=normalized, request_id=request_id)
        except FirewallAdminError as e:
            self._logger.warning(
                "firewall_admin.unblock_rejected", user_id=user_id, ip=normalized,
                code=e.code, request_id=request_id,
            )
            raise
        self._logger.info(
            "firewall_admin.unblock", user_id=user_id, ip=normalized,
            removed=result.removed, dry_run=result.dry_run,
            already_absent=result.already_absent, request_id=request_id,
        )
        return result
