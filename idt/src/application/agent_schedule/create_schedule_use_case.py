"""CreateScheduleUseCase: 에이전트 스케줄 생성."""
import uuid
from datetime import datetime, timezone

from src.application.agent_schedule.access import ensure_owned_agent
from src.application.agent_schedule.schemas import (
    CreateScheduleRequest,
    ScheduleResponse,
)
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_schedule.entity import AgentSchedule
from src.domain.agent_schedule.interfaces import ScheduleRepositoryInterface
from src.domain.agent_schedule.policies import SchedulePolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class CreateScheduleUseCase:
    def __init__(
        self,
        schedule_repo: ScheduleRepositoryInterface,
        agent_repo: AgentDefinitionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._schedule_repo = schedule_repo
        self._agent_repo = agent_repo
        self._logger = logger

    async def execute(
        self,
        agent_id: str,
        user_id: str,
        request: CreateScheduleRequest,
        request_id: str,
    ) -> ScheduleResponse:
        self._logger.info(
            "CreateScheduleUseCase start", request_id=request_id, agent_id=agent_id
        )
        try:
            await ensure_owned_agent(
                self._agent_repo, agent_id, user_id, request_id
            )
            count = await self._schedule_repo.count_by_agent(agent_id, request_id)
            SchedulePolicy.validate_count(count)

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            spec = request.spec.to_domain()
            SchedulePolicy.validate_instruction(request.instruction)
            SchedulePolicy.validate_spec(spec, request.timezone, now)

            schedule = AgentSchedule(
                id=str(uuid.uuid4()),
                agent_id=agent_id,
                user_id=user_id,
                name=request.name,
                spec=spec,
                instruction=request.instruction,
                enabled=request.enabled,
                timezone=request.timezone,
                next_run_at=SchedulePolicy.compute_next_run(
                    spec, request.timezone, now
                ),
                last_run_at=None,
                created_at=now,
                updated_at=now,
            )
            await self._schedule_repo.save(schedule, request_id)
            self._logger.info(
                "CreateScheduleUseCase done",
                request_id=request_id,
                schedule_id=schedule.id,
            )
            return ScheduleResponse.from_entity(schedule)
        except Exception as e:
            self._logger.error(
                "CreateScheduleUseCase failed", exception=e, request_id=request_id
            )
            raise
