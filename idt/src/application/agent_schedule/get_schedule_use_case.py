"""GetScheduleUseCase: 스케줄 단건 조회."""
from src.application.agent_schedule.access import get_owned_schedule
from src.application.agent_schedule.schemas import ScheduleResponse
from src.domain.agent_schedule.interfaces import ScheduleRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class GetScheduleUseCase:
    def __init__(
        self,
        schedule_repo: ScheduleRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._schedule_repo = schedule_repo
        self._logger = logger

    async def execute(
        self, agent_id: str, schedule_id: str, user_id: str, request_id: str
    ) -> ScheduleResponse:
        try:
            schedule = await get_owned_schedule(
                self._schedule_repo, agent_id, schedule_id, user_id, request_id
            )
            return ScheduleResponse.from_entity(schedule)
        except Exception as e:
            self._logger.error(
                "GetScheduleUseCase failed", exception=e, request_id=request_id
            )
            raise
