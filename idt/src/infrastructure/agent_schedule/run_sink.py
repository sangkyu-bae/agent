"""DbScheduleRunSink: 실행 이력 기록 sink (ScheduleRunSinkInterface 기본 구현).

에이전트 실행(수십 초)과 이력 기록의 트랜잭션을 분리하기 위해 on_started /
on_finished 각각 자체 짧은 트랜잭션으로 즉시 커밋한다.
session_factory 주입 선례: RunAgentUseCase (src/api/main.py, FK 락 회피).
"""
import uuid
from datetime import datetime, timezone

from src.domain.agent_schedule.entity import AgentSchedule, RunStatus
from src.domain.agent_schedule.interfaces import ScheduleRunSinkInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.agent_schedule.models import AgentScheduleRunModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DbScheduleRunSink(ScheduleRunSinkInterface):
    def __init__(self, session_factory, logger: LoggerInterface) -> None:
        self._session_factory = session_factory
        self._logger = logger

    async def on_started(
        self, schedule: AgentSchedule, scheduled_for: datetime, request_id: str
    ) -> str:
        run_record_id = str(uuid.uuid4())
        async with self._session_factory() as session:
            async with session.begin():
                session.add(
                    AgentScheduleRunModel(
                        id=run_record_id,
                        schedule_id=schedule.id,
                        agent_id=schedule.agent_id,
                        status="running",
                        scheduled_for=scheduled_for,
                        started_at=_utc_now(),
                        request_id=request_id,
                    )
                )
        self._logger.info(
            "schedule run started",
            request_id=request_id,
            schedule_id=schedule.id,
            run_record_id=run_record_id,
        )
        return run_record_id

    async def on_finished(
        self,
        run_record_id: str,
        status: RunStatus,
        request_id: str,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        error_message: str | None = None,
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                model = await session.get(AgentScheduleRunModel, run_record_id)
                if model is None:
                    raise ValueError(
                        f"실행 이력을 찾을 수 없습니다: {run_record_id}"
                    )
                model.status = status
                model.finished_at = _utc_now()
                model.session_id = session_id
                model.run_id = run_id
                model.error_message = error_message
        self._logger.info(
            "schedule run finished",
            request_id=request_id,
            run_record_id=run_record_id,
            status=status,
        )
