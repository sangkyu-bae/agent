"""ListScheduleRunsUseCase: 스케줄 실행 이력 조회 (페이지네이션)."""
from src.application.agent_schedule.access import get_owned_schedule
from src.application.agent_schedule.schemas import ScheduleRunResponse
from src.domain.agent_schedule.interfaces import (
    ScheduleRepositoryInterface,
    ScheduleRunRepositoryInterface,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_MAX_LIMIT = 100


class ListScheduleRunsUseCase:
    def __init__(
        self,
        schedule_repo: ScheduleRepositoryInterface,
        run_repo: ScheduleRunRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._schedule_repo = schedule_repo
        self._run_repo = run_repo
        self._logger = logger

    async def execute(
        self,
        agent_id: str,
        schedule_id: str,
        user_id: str,
        limit: int,
        offset: int,
        request_id: str,
    ) -> list[ScheduleRunResponse]:
        try:
            await get_owned_schedule(
                self._schedule_repo, agent_id, schedule_id, user_id, request_id
            )
            runs = await self._run_repo.list_by_schedule(
                schedule_id, min(limit, _MAX_LIMIT), offset, request_id
            )
            return [ScheduleRunResponse.from_entity(r) for r in runs]
        except Exception as e:
            self._logger.error(
                "ListScheduleRunsUseCase failed", exception=e, request_id=request_id
            )
            raise
