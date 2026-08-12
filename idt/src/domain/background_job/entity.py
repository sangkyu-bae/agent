"""background-jobs 도메인 엔티티: BackgroundJob.

시각 규격: 모든 datetime 은 UTC naive (agent_schedule 관례 동일).
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

JobStatus = Literal["queued", "running", "success", "failed"]
JobSource = Literal["chat", "api"]


@dataclass
class BackgroundJob:
    id: str
    user_id: str  # 등록자 = 실행 신원 (D3)
    agent_id: str
    source: str  # chat|api
    query: str
    session_id: str | None  # 미지정 시 실행 시 생성 후 역기입
    run_id: str | None  # ai_run 연결 (AGENT-OBS-001)
    status: JobStatus
    error_message: str | None
    seen_at: datetime | None  # NULL=미확인 (벨 배지 기준)
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    request_id: str
    created_at: datetime
    updated_at: datetime
