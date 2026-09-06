"""ListMySchedulesUseCase: 내 스케줄 정의 조회 (jobs-page-revamp FR-15).

작업함 '스케줄 작업' 탭 전용 read-only — 기존 agent_schedule CRUD 계약은
그대로 두고, 에이전트를 가로지르는 조회만 추가한다(additive).
list_my_schedule_runs_use_case.py 와 같은 자리·같은 형태를 따른다.
"""
from src.application.background_job.schemas import MyScheduleResponse
from src.domain.agent_schedule.interfaces import ScheduleRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ListMySchedulesUseCase:
    def __init__(
        self,
        schedule_repo: ScheduleRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._schedule_repo = schedule_repo
        self._logger = logger

    async def execute(
        self, user_id: str, request_id: str
    ) -> list[MyScheduleResponse]:
        rows = await self._schedule_repo.list_by_user(user_id, request_id)
        return [
            MyScheduleResponse.from_entity(schedule, agent_name)
            for schedule, agent_name in rows
        ]
