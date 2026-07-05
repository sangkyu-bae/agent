"""agent-schedule application 스키마 (요청/응답 + 도메인 변환)."""
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field

from src.domain.agent_schedule.entity import AgentSchedule, ScheduleRun
from src.domain.agent_schedule.value_objects import ScheduleSpec


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


class ScheduleSpecPayload(BaseModel):
    schedule_type: Literal["once", "daily", "weekly", "cron"]
    run_date: date | None = None
    time_of_day: time | None = None
    days_of_week: list[int] | None = None
    cron_expr: str | None = None

    def to_domain(self) -> ScheduleSpec:
        return ScheduleSpec(
            schedule_type=self.schedule_type,
            run_date=self.run_date,
            time_of_day=self.time_of_day,
            days_of_week=(
                tuple(self.days_of_week) if self.days_of_week is not None else None
            ),
            cron_expr=self.cron_expr,
        )

    @classmethod
    def from_domain(cls, spec: ScheduleSpec) -> "ScheduleSpecPayload":
        return cls(
            schedule_type=spec.schedule_type,
            run_date=spec.run_date,
            time_of_day=spec.time_of_day,
            days_of_week=(
                list(spec.days_of_week) if spec.days_of_week is not None else None
            ),
            cron_expr=spec.cron_expr,
        )


class CreateScheduleRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    spec: ScheduleSpecPayload
    # R9: 지침. {today}/{now}/{weekday} 플레이스홀더 사용 가능
    instruction: str = Field(..., min_length=1, max_length=1900)
    timezone: str = "Asia/Seoul"
    enabled: bool = True


class UpdateScheduleRequest(CreateScheduleRequest):
    pass


class ToggleScheduleRequest(BaseModel):
    enabled: bool


class ScheduleResponse(BaseModel):
    id: str
    agent_id: str
    name: str
    spec: ScheduleSpecPayload
    instruction: str
    enabled: bool
    timezone: str
    next_run_at: str | None
    last_run_at: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_entity(cls, entity: AgentSchedule) -> "ScheduleResponse":
        return cls(
            id=entity.id,
            agent_id=entity.agent_id,
            name=entity.name,
            spec=ScheduleSpecPayload.from_domain(entity.spec),
            instruction=entity.instruction,
            enabled=entity.enabled,
            timezone=entity.timezone,
            next_run_at=_iso(entity.next_run_at),
            last_run_at=_iso(entity.last_run_at),
            created_at=entity.created_at.isoformat(),
            updated_at=entity.updated_at.isoformat(),
        )


class ScheduleRunResponse(BaseModel):
    id: str
    schedule_id: str
    status: str
    scheduled_for: str
    started_at: str
    finished_at: str | None
    session_id: str | None
    run_id: str | None
    error_message: str | None

    @classmethod
    def from_entity(cls, run: ScheduleRun) -> "ScheduleRunResponse":
        return cls(
            id=run.id,
            schedule_id=run.schedule_id,
            status=run.status,
            scheduled_for=run.scheduled_for.isoformat(),
            started_at=run.started_at.isoformat(),
            finished_at=_iso(run.finished_at),
            session_id=run.session_id,
            run_id=run.run_id,
            error_message=run.error_message,
        )


class TriggerResponse(BaseModel):
    claimed: int
    success: int
    failed: int
    request_id: str


class TriggerStatusResponse(BaseModel):
    last_triggered_at: str | None
    last_result: TriggerResponse | None
