"""UpdateScheduleUseCase: 스케줄 수정 (spec/tz 변경 시 next_run_at 재계산)."""
from datetime import datetime, timezone

from src.application.agent_schedule.access import get_owned_schedule
from src.application.agent_schedule.schemas import (
    ScheduleResponse,
    UpdateScheduleRequest,
)
from src.domain.agent_schedule.interfaces import ScheduleRepositoryInterface
from src.domain.agent_schedule.policies import SchedulePolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class UpdateScheduleUseCase:
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
        request: UpdateScheduleRequest,
        request_id: str,
    ) -> ScheduleResponse:
        try:
            schedule = await get_owned_schedule(
                self._schedule_repo, agent_id, schedule_id, user_id, request_id
            )
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            spec = request.spec.to_domain()
            SchedulePolicy.validate_instruction(request.instruction)
            SchedulePolicy.validate_spec(spec, request.timezone, now)

            schedule.name = request.name
            schedule.spec = spec
            schedule.instruction = request.instruction
            schedule.timezone = request.timezone
            schedule.enabled = request.enabled
            # spec/tz 변경 여부와 무관하게 항상 재계산 — 안전하며 결과 동일
            schedule.next_run_at = SchedulePolicy.compute_next_run(
                spec, request.timezone, now
            )
            schedule.updated_at = now

            await self._schedule_repo.update(schedule, request_id)
            self._logger.info(
                "UpdateScheduleUseCase done",
                request_id=request_id,
                schedule_id=schedule_id,
            )
            return ScheduleResponse.from_entity(schedule)
        except Exception as e:
            self._logger.error(
                "UpdateScheduleUseCase failed", exception=e, request_id=request_id
            )
            raise
