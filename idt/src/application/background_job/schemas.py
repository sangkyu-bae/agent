"""background-jobs 요청/응답 DTO (Design §4-5)."""
from datetime import datetime

from pydantic import BaseModel, Field

from src.domain.background_job.entity import BackgroundJob


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


class UnseenCountResponse(BaseModel):
    count: int


class SeenAllResponse(BaseModel):
    updated: int


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
