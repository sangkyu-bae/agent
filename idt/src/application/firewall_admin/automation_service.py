"""방화벽 자동 점검 — 보안 에이전트의 스케줄·알림 수신 켜기/끄기.

Design Ref: firewall-agent design §4.4 (Plan FR-15~17).
- 대상 에이전트는 설정 FIREWALL_ADMIN_AGENT_ID 하나다. 비었거나 없으면
configured=false(200).
- 소유자 검사 대신 라우터의 admin 역할이 권한이다. 누가 무엇을 바꿨는지 로그에 남긴다.
"""

from __future__ import annotations

from src.application.firewall_admin.ports import AutomationPort
from src.domain.firewall_admin.errors import AutomationNotConfiguredError
from src.domain.firewall_admin.models import AutomationState
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class FirewallAutomationService:
    def __init__(
        self, port: AutomationPort, *, agent_id: str, logger: LoggerInterface
    ) -> None:
        self._port = port
        self._agent_id = (agent_id or "").strip()
        self._logger = logger

    async def state(self) -> AutomationState:
        if not self._agent_id:
            return AutomationState(
                configured=False, reason="AGENT_NOT_SET", snapshot=None
            )
        snapshot = await self._port.load(self._agent_id)
        if snapshot is None:
            return AutomationState(
                configured=False, reason="AGENT_NOT_FOUND", snapshot=None
            )
        return AutomationState(configured=True, reason=None, snapshot=snapshot)

    async def update(
        self,
        *,
        schedule_enabled: bool | None,
        alert_enabled: bool | None,
        admin_user_id: str,
    ) -> AutomationState:
        if not self._agent_id or (schedule_enabled is None and alert_enabled is None):
            raise AutomationNotConfiguredError()
        before = await self.state()
        if not before.configured:
            raise AutomationNotConfiguredError()
        if schedule_enabled is not None:
            if (
                await self._port.set_schedules_enabled(self._agent_id, schedule_enabled)
                == 0
            ):
                raise AutomationNotConfiguredError("보안 에이전트에 스케줄이 없습니다")
        if alert_enabled is not None:
            if not await self._port.set_alert_enabled(self._agent_id, alert_enabled):
                raise AutomationNotConfiguredError(
                    "보안 에이전트에 알림 수신 설정이 없습니다"
                )
        self._logger.info(
            "firewall automation changed",
            admin_user_id=admin_user_id,
            agent_id=self._agent_id,
            schedule_enabled=schedule_enabled,
            alert_enabled=alert_enabled,
            schedules_before=[s.enabled for s in before.snapshot.schedules],
            alert_before=before.snapshot.alert.enabled,
        )
        return await self.state()
