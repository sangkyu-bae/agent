"""DeleteScheduleUseCase: 스케줄 삭제."""
from src.application.agent_schedule.access import get_owned_schedule
from src.domain.agent_schedule.interfaces import ScheduleRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class DeleteScheduleUseCase:
    def __init__(
        self,
        schedule_repo: ScheduleRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._schedule_repo = schedule_repo
        self._logger = logger

    async def execute(
        self, agent_id: str, schedule_id: str, user_id: str, request_id: str
    ) -> None:
        try:
            await get_owned_schedule(
                self._schedule_repo, agent_id, schedule_id, user_id, request_id
            )
            await self._schedule_repo.delete(schedule_id, request_id)
            self._logger.info(
                "DeleteScheduleUseCase done",
                request_id=request_id,
                schedule_id=schedule_id,
            )
        except Exception as e:
            self._logger.error(
                "DeleteScheduleUseCase failed", exception=e, request_id=request_id
            )
            raise
