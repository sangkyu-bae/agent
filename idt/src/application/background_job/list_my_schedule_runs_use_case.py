"""ListMyScheduleRunsUseCase: 내 스케줄 실행 이력 조회 (Design D9 — read-only).

작업함 "스케줄 실행" 탭 전용 — 기존 agent_schedule CRUD·트리거 계약 무변경.
"""
from src.application.background_job.schemas import MyScheduleRunResponse
from src.domain.agent_schedule.interfaces import ScheduleRunRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ListMyScheduleRunsUseCase:
    def __init__(
        self,
        schedule_run_repo: ScheduleRunRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._schedule_run_repo = schedule_run_repo
        self._logger = logger

    async def execute(
        self, user_id: str, limit: int, offset: int, request_id: str
    ) -> list[MyScheduleRunResponse]:
        rows = await self._schedule_run_repo.list_by_user(
            user_id, limit, offset, request_id
        )
        return [
            MyScheduleRunResponse(
                id=run.id,
                schedule_id=run.schedule_id,
                schedule_name=name,
                agent_id=run.agent_id,
                agent_name=agent_name,
                status=run.status,
                scheduled_for=run.scheduled_for,
                started_at=run.started_at,
                finished_at=run.finished_at,
                session_id=run.session_id,
                error_message=run.error_message,
            )
            for run, name, agent_name in rows
        ]
