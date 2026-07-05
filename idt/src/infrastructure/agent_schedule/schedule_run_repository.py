"""ScheduleRunRepository: agent_schedule_run 이력 저장소 (DB-001 준수)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent_schedule.entity import ScheduleRun
from src.domain.agent_schedule.interfaces import ScheduleRunRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.agent_schedule.models import AgentScheduleRunModel


def _to_entity(model: AgentScheduleRunModel) -> ScheduleRun:
    return ScheduleRun(
        id=model.id,
        schedule_id=model.schedule_id,
        agent_id=model.agent_id,
        status=model.status,
        scheduled_for=model.scheduled_for,
        started_at=model.started_at,
        finished_at=model.finished_at,
        session_id=model.session_id,
        run_id=model.run_id,
        error_message=model.error_message,
        request_id=model.request_id,
    )


class ScheduleRunRepository(ScheduleRunRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(self, run: ScheduleRun, request_id: str) -> None:
        model = AgentScheduleRunModel(
            id=run.id,
            schedule_id=run.schedule_id,
            agent_id=run.agent_id,
            status=run.status,
            scheduled_for=run.scheduled_for,
            started_at=run.started_at,
            finished_at=run.finished_at,
            session_id=run.session_id,
            run_id=run.run_id,
            error_message=run.error_message,
            request_id=run.request_id,
        )
        self._session.add(model)
        await self._session.flush()

    async def update(self, run: ScheduleRun, request_id: str) -> None:
        model = await self._session.get(AgentScheduleRunModel, run.id)
        if model is None:
            raise ValueError(f"실행 이력을 찾을 수 없습니다: {run.id}")
        model.status = run.status
        model.finished_at = run.finished_at
        model.session_id = run.session_id
        model.run_id = run.run_id
        model.error_message = run.error_message
        await self._session.flush()

    async def find_by_id(
        self, run_record_id: str, request_id: str
    ) -> ScheduleRun | None:
        model = await self._session.get(AgentScheduleRunModel, run_record_id)
        return _to_entity(model) if model is not None else None

    async def list_by_schedule(
        self, schedule_id: str, limit: int, offset: int, request_id: str
    ) -> list[ScheduleRun]:
        stmt = (
            select(AgentScheduleRunModel)
            .where(AgentScheduleRunModel.schedule_id == schedule_id)
            .order_by(AgentScheduleRunModel.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return [_to_entity(m) for m in result.scalars().all()]
