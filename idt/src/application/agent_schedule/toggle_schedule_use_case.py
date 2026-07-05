"""ToggleScheduleUseCase: 스케줄 on/off.

off→on 시 next_run_at 을 현재 시각 이후로 재계산 — 꺼둔 사이 지나간 시각으로
즉시 발화하는 사고를 방지한다 (Design §5.1).
"""
from datetime import datetime, timezone

from src.application.agent_schedule.access import get_owned_schedule
from src.application.agent_schedule.schemas import ScheduleResponse
from src.domain.agent_schedule.interfaces import ScheduleRepositoryInterface
from src.domain.agent_schedule.policies import SchedulePolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ToggleScheduleUseCase:
    def __init__(
        self,
        schedule_repo: ScheduleRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._schedule_repo = schedule_repo
        self._logger = logger

    async def execute(
        self,
        agent_id: str,
        schedule_id: str,
        user_id: str,
        enabled: bool,
        request_id: str,
    ) -> ScheduleResponse:
        try:
            schedule = await get_owned_schedule(
                self._schedule_repo, agent_id, schedule_id, user_id, request_id
            )
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            if enabled and not schedule.enabled:
                schedule.next_run_at = SchedulePolicy.compute_next_run(
                    schedule.spec, schedule.timezone, now
                )
            schedule.enabled = enabled
            schedule.updated_at = now
            await self._schedule_repo.update(schedule, request_id)
            self._logger.info(
                "ToggleScheduleUseCase done",
                request_id=request_id,
                schedule_id=schedule_id,
                enabled=enabled,
            )
            return ScheduleResponse.from_entity(schedule)
        except Exception as e:
            self._logger.error(
                "ToggleScheduleUseCase failed", exception=e, request_id=request_id
            )
            raise
