"""background-jobs 요청/응답 DTO (Design §4-5)."""
from datetime import datetime

from pydantic import BaseModel, Field

from src.application.agent_schedule.schemas import (
    ScheduleResponse,
    ScheduleSpecPayload,
)
from src.domain.agent_schedule.entity import AgentSchedule
from src.domain.background_job.entity import BackgroundJob, JobHistoryItem


class EnqueueJobRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = None
    source: str = Field(default="chat", pattern="^(chat|api)$")


class EnqueueJobResponse(BaseModel):
    job_id: str
    status: str
    request_id: str


class JobResponse(BaseModel):
    id: str
    agent_id: str
    # 작업함 표시용 에이전트명 — additive, 목록 조회 시 JOIN 으로 채운다
    agent_name: str | None = None
    source: str
    query: str
    session_id: str | None
    run_id: str | None
    status: str
    error_message: str | None
    seen_at: datetime | None
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_entity(
        cls, job: BackgroundJob, agent_name: str | None = None
    ) -> "JobResponse":
        return cls(
            id=job.id,
            agent_id=job.agent_id,
            agent_name=agent_name,
            source=job.source,
            query=job.query,
            session_id=job.session_id,
            run_id=job.run_id,
            status=job.status,
            error_message=job.error_message,
            seen_at=job.seen_at,
            queued_at=job.queued_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )


class JobHistoryResponse(BaseModel):
    """작업 기록 탭의 한 행 — 수동 job 과 스케줄 실행 공통 (jobs-page-revamp §4.2)."""

    id: str
    type: str  # manual | schedule
    occurred_at: datetime
    title: str
    status: str
    agent_id: str
    agent_name: str | None
    session_id: str | None
    error_message: str | None
    seen_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    deletable: bool

    @classmethod
    def from_item(cls, item: JobHistoryItem) -> "JobHistoryResponse":
        return cls(
            id=item.id,
            type=item.type,
            occurred_at=item.occurred_at,
            title=item.title,
            status=item.status,
            agent_id=item.agent_id,
            agent_name=item.agent_name,
            session_id=item.session_id,
            error_message=item.error_message,
            seen_at=item.seen_at,
            started_at=item.started_at,
            finished_at=item.finished_at,
            deletable=item.deletable,
        )


class JobListResponse(BaseModel):
    """페이지네이션 응답 — total 없이는 '1 / N 페이지'를 그릴 수 없다 (FR-06)."""

    items: list[JobHistoryResponse]
    total: int


class CleanupJobsResponse(BaseModel):
    deleted: int


class UnseenCountResponse(BaseModel):
    """벨 배지 미확인 건수.

    approval-gate Design §5.5: `count` 의 의미(총 미확인)는 그대로 두고
    분해 필드를 **추가**한다 — 기존 소비자(AppSidebar 등)를 깨지 않으면서
    필요한 화면만 분해 표시할 수 있다.
    """

    count: int
    jobs: int = 0
    approvals: int = 0


class SeenAllResponse(BaseModel):
    updated: int


class MyScheduleResponse(BaseModel):
    """작업함 '스케줄 작업' 탭 — 내 스케줄 정의 (jobs-page-revamp FR-15).

    관리(수정·토글·삭제)는 기존 /agents/{id}/schedules 계약을 그대로 쓰므로
    agent_id 를 함께 내려 프론트가 그 경로를 조립할 수 있게 한다.
    """

    id: str
    agent_id: str
    # 작업함 표시용 에이전트명 — 에이전트 삭제 시 None
    agent_name: str | None = None
    name: str
    spec: ScheduleSpecPayload
    instruction: str
    enabled: bool
    timezone: str
    next_run_at: str | None
    last_run_at: str | None

    @classmethod
    def from_entity(
        cls, schedule: AgentSchedule, agent_name: str | None
    ) -> "MyScheduleResponse":
        base = ScheduleResponse.from_entity(schedule)
        return cls(
            id=base.id,
            agent_id=base.agent_id,
            agent_name=agent_name,
            name=base.name,
            spec=base.spec,
            instruction=base.instruction,
            enabled=base.enabled,
            timezone=base.timezone,
            next_run_at=base.next_run_at,
            last_run_at=base.last_run_at,
        )


class MyScheduleRunResponse(BaseModel):
    id: str
    schedule_id: str
    schedule_name: str
    agent_id: str
    # 작업함 표시용 에이전트명 — additive (에이전트 삭제 시 None)
    agent_name: str | None = None
    status: str
    scheduled_for: datetime
    started_at: datetime
    finished_at: datetime | None
    session_id: str | None
    error_message: str | None
