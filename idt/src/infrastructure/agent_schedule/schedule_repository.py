"""ScheduleRepository: agent_schedule 저장소.

commit/rollback 호출 금지 — 트랜잭션 경계는 호출측(get_session dependency 또는
TriggerDueSchedulesUseCase 의 session_factory 블록)이 소유한다 (DB-001).
"""
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent_schedule.entity import AgentSchedule
from src.domain.agent_schedule.interfaces import (
    ClaimedSchedule,
    ScheduleRepositoryInterface,
)
from src.domain.agent_schedule.policies import SchedulePolicy
from src.domain.agent_schedule.value_objects import ScheduleSpec
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.agent_schedule.models import AgentScheduleModel


def _to_spec(model: AgentScheduleModel) -> ScheduleSpec:
    return ScheduleSpec(
        schedule_type=model.schedule_type,
        run_date=model.run_date,
        time_of_day=model.time_of_day,
        days_of_week=(
            tuple(model.days_of_week) if model.days_of_week is not None else None
        ),
        cron_expr=model.cron_expr,
    )


def _to_entity(model: AgentScheduleModel) -> AgentSchedule:
    return AgentSchedule(
        id=model.id,
        agent_id=model.agent_id,
        user_id=model.user_id,
        name=model.name,
        spec=_to_spec(model),
        instruction=model.instruction,
        enabled=model.enabled,
        timezone=model.timezone,
        next_run_at=model.next_run_at,
        last_run_at=model.last_run_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _apply_entity(model: AgentScheduleModel, entity: AgentSchedule) -> None:
    model.name = entity.name
    model.schedule_type = entity.spec.schedule_type
    model.run_date = entity.spec.run_date
    model.time_of_day = entity.spec.time_of_day
    model.days_of_week = (
        list(entity.spec.days_of_week)
        if entity.spec.days_of_week is not None
        else None
    )
    model.cron_expr = entity.spec.cron_expr
    model.instruction = entity.instruction
    model.enabled = entity.enabled
    model.timezone = entity.timezone
    model.next_run_at = entity.next_run_at
    model.last_run_at = entity.last_run_at
    model.updated_at = entity.updated_at


class ScheduleRepository(ScheduleRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(self, schedule: AgentSchedule, request_id: str) -> None:
        model = AgentScheduleModel(
            id=schedule.id,
            agent_id=schedule.agent_id,
            user_id=schedule.user_id,
            created_at=schedule.created_at,
        )
        _apply_entity(model, schedule)
        self._session.add(model)
        await self._session.flush()
        self._logger.info(
            "schedule saved", request_id=request_id, schedule_id=schedule.id
        )

    async def find_by_id(
        self, schedule_id: str, request_id: str
    ) -> AgentSchedule | None:
        model = await self._session.get(AgentScheduleModel, schedule_id)
        return _to_entity(model) if model is not None else None

    async def list_by_agent(
        self, agent_id: str, request_id: str
    ) -> list[AgentSchedule]:
        stmt = (
            select(AgentScheduleModel)
            .where(AgentScheduleModel.agent_id == agent_id)
            .order_by(AgentScheduleModel.created_at)
        )
        result = await self._session.execute(stmt)
        return [_to_entity(m) for m in result.scalars().all()]

    async def count_by_agent(self, agent_id: str, request_id: str) -> int:
        stmt = select(func.count()).select_from(AgentScheduleModel).where(
            AgentScheduleModel.agent_id == agent_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def update(self, schedule: AgentSchedule, request_id: str) -> None:
        model = await self._session.get(AgentScheduleModel, schedule.id)
        if model is None:
            raise ValueError(f"스케줄을 찾을 수 없습니다: {schedule.id}")
        _apply_entity(model, schedule)
        await self._session.flush()

    async def delete(self, schedule_id: str, request_id: str) -> None:
        stmt = delete(AgentScheduleModel).where(
            AgentScheduleModel.id == schedule_id
        )
        await self._session.execute(stmt)
        await self._session.flush()
        self._logger.info(
            "schedule deleted", request_id=request_id, schedule_id=schedule_id
        )

    async def claim_due(
        self, now_utc: datetime, request_id: str
    ) -> list[ClaimedSchedule]:
        """due 스케줄 선점 (Design §3-4).

        FOR UPDATE SKIP LOCKED 로 잠긴 행을 건너뛰어 동시 트리거 호출 간
        이중 클레임을 방지한다. next_run_at 재계산(UPDATE)까지 이 안에서 수행
        — commit 은 호출측 트랜잭션 블록이 담당.
        """
        stmt = (
            select(AgentScheduleModel)
            .where(
                AgentScheduleModel.enabled.is_(True),
                AgentScheduleModel.next_run_at <= now_utc,
            )
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()

        claimed: list[ClaimedSchedule] = []
        for model in models:
            scheduled_for = model.next_run_at
            nxt = SchedulePolicy.compute_next_run(
                _to_spec(model), model.timezone, after_utc=now_utc
            )
            model.next_run_at = nxt
            if nxt is None:  # once 소진
                model.enabled = False
            model.updated_at = now_utc
            claimed.append(
                ClaimedSchedule(schedule=_to_entity(model), scheduled_for=scheduled_for)
            )
        await self._session.flush()
        self._logger.info(
            "schedules claimed", request_id=request_id, count=len(claimed)
        )
        return claimed

    async def touch_last_run(
        self, schedule_id: str, ran_at: datetime, request_id: str
    ) -> None:
        stmt = (
            update(AgentScheduleModel)
            .where(AgentScheduleModel.id == schedule_id)
            .values(last_run_at=ran_at)
        )
        await self._session.execute(stmt)
        await self._session.flush()
