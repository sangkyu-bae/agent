"""AutomationPort 구현 — 보안 에이전트의 스케줄·알림 수신 상태 (요청 세션).

Design Ref: firewall-agent design §4.4.
스케줄을 켤 때 next_run_at 을 다시 계산한다(ToggleScheduleUseCase 와 같은 규칙: 켤 때만
재계산,
끌 때는 그대로 두고 claim_due 가 enabled 로 거른다). 커밋은 요청 세션(get_session)이
한다.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent_schedule.policies import SchedulePolicy
from src.domain.firewall_admin.models import (
    AutomationAlert,
    AutomationRun,
    AutomationSchedule,
    AutomationSnapshot,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.agent_alert.repository import (
    AlertReceiptRepository,
    AlertReceiverRepository,
)
from src.infrastructure.agent_builder.models import AgentDefinitionModel
from src.infrastructure.agent_schedule.schedule_repository import ScheduleRepository
from src.infrastructure.agent_schedule.schedule_run_repository import (
    ScheduleRunRepository,
)

_RID = "firewall-automation"


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class AutomationAdapter:
    def __init__(
        self,
        session: AsyncSession,
        logger: LoggerInterface,
        now_fn: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._session = session
        self._schedules = ScheduleRepository(session=session, logger=logger)
        self._runs = ScheduleRunRepository(session=session, logger=logger)
        self._receivers = AlertReceiverRepository(session, logger)
        self._receipts = AlertReceiptRepository(session, logger)
        self._now_fn = now_fn

    async def load(self, agent_id: str) -> AutomationSnapshot | None:
        name = (
            await self._session.execute(
                select(AgentDefinitionModel.name).where(
                    AgentDefinitionModel.id == agent_id
                )
            )
        ).scalar_one_or_none()
        if name is None:
            return None
        schedules = []
        for schedule in await self._schedules.list_by_agent(agent_id, _RID):
            last = await self._runs.list_by_schedule(schedule.id, 1, 0, _RID)
            schedules.append(
                AutomationSchedule(
                    id=schedule.id,
                    name=schedule.name,
                    enabled=schedule.enabled,
                    cron_expr=schedule.spec.cron_expr,
                    skip_when_busy=schedule.skip_when_busy,
                    next_run_at=schedule.next_run_at,
                    last_run=(
                        AutomationRun(
                            status=last[0].status,
                            skip_reason=last[0].skip_reason,
                            started_at=last[0].started_at,
                        )
                        if last
                        else None
                    ),
                )
            )
        return AutomationSnapshot(
            agent_id=agent_id,
            agent_name=name,
            schedules=tuple(schedules),
            alert=await self._alert(agent_id),
        )

    async def _alert(self, agent_id: str) -> AutomationAlert:
        receiver = await self._receivers.find_by_agent_id(agent_id, _RID)
        if receiver is None:
            return AutomationAlert(
                configured=False,
                enabled=None,
                skip_when_busy=None,
                last_result=None,
                last_received_at=None,
            )
        last = await self._receipts.list_recent(receiver.id, 1, _RID)
        return AutomationAlert(
            configured=True,
            enabled=receiver.enabled,
            skip_when_busy=receiver.skip_when_busy,
            last_result=last[0].result if last else None,
            last_received_at=last[0].received_at if last else None,
        )

    async def set_schedules_enabled(self, agent_id: str, enabled: bool) -> int:
        schedules = await self._schedules.list_by_agent(agent_id, _RID)
        now = self._now_fn()
        for schedule in schedules:
            if schedule.enabled == enabled:
                continue
            if enabled:
                schedule.next_run_at = SchedulePolicy.compute_next_run(
                    schedule.spec, schedule.timezone, now
                )
            schedule.enabled = enabled
            schedule.updated_at = now
            await self._schedules.update(schedule, _RID)
        return len(schedules)

    async def set_alert_enabled(self, agent_id: str, enabled: bool) -> bool:
        receiver = await self._receivers.find_by_agent_id(agent_id, _RID)
        if receiver is None:
            return False
        if receiver.enabled != enabled:
            receiver.enabled = enabled
            receiver.updated_at = self._now_fn()
            await self._receivers.update(receiver, _RID)
        return True
