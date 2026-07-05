"""ListSchedulesUseCase: 에이전트의 스케줄 목록 조회."""
from src.application.agent_schedule.access import ensure_owned_agent
from src.application.agent_schedule.schemas import ScheduleResponse
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_schedule.interfaces import ScheduleRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ListSchedulesUseCase:
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
        self, agent_id: str, user_id: str, request_id: str
    ) -> list[ScheduleResponse]:
        try:
            await ensure_owned_agent(
                self._agent_repo, agent_id, user_id, request_id
            )
            schedules = await self._schedule_repo.list_by_agent(
                agent_id, request_id
            )
            return [ScheduleResponse.from_entity(s) for s in schedules]
        except Exception as e:
            self._logger.error(
                "ListSchedulesUseCase failed", exception=e, request_id=request_id
            )
            raise
