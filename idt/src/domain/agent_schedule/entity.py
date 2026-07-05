"""agent-schedule 도메인 엔티티: AgentSchedule, ScheduleRun.

시각 규격: 모든 datetime 은 UTC naive.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from src.domain.agent_schedule.value_objects import ScheduleSpec

RunStatus = Literal["running", "success", "failed"]


@dataclass
class AgentSchedule:
    id: str
    agent_id: str
    user_id: str  # 생성자 = 실행 주체
    name: str
    spec: ScheduleSpec
    instruction: str  # R9: 실행 시 렌더링 → user 질문
    enabled: bool
    timezone: str
    next_run_at: datetime | None  # 판정 키. once 소진/disable 시 None
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass
class ScheduleRun:
    id: str
    schedule_id: str
    agent_id: str  # 스케줄 삭제 후에도 이력 추적 가능하도록 비정규화
    status: RunStatus
    scheduled_for: datetime  # 원래 예정 시각
    started_at: datetime
    finished_at: datetime | None
    session_id: str | None
    run_id: str | None  # ai_run 연결 (AGENT-OBS-001)
    error_message: str | None
    request_id: str
