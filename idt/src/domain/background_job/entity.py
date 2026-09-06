"""background-jobs 도메인 엔티티: BackgroundJob.

시각 규격: 모든 datetime 은 UTC naive (agent_schedule 관례 동일).
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

JobStatus = Literal["queued", "running", "success", "failed"]
JobSource = Literal["chat", "api"]

# jobs-page-revamp Design §3.1 — 통합 이력의 소스 구분
JobHistoryType = Literal["manual", "schedule"]


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
    # jobs-page-revamp Design §3.1 — NULL=활성. 값이 있으면 조회·집계에서 제외
    deleted_at: datetime | None = None


@dataclass(frozen=True)
class JobHistoryItem:
    """작업 기록 탭의 한 행 — 수동 job 과 스케줄 실행을 하나로 정규화한 읽기 전용 뷰.

    Design Ref: §3.1 — 두 테이블의 컬럼 차이는 repository 가 흡수하고,
    위 레이어는 이 DTO 하나만 본다.
    """

    id: str
    type: JobHistoryType
    occurred_at: datetime  # job=queued_at, schedule=scheduled_for (정렬 기준)
    title: str  # job=query, schedule=스케줄명
    status: JobStatus
    agent_id: str
    agent_name: str | None
    session_id: str | None
    error_message: str | None
    seen_at: datetime | None  # 스케줄 행은 항상 None
    started_at: datetime | None
    finished_at: datetime | None

    @property
    def deletable(self) -> bool:
        """휴지통 노출 기준 (FR-11) — 스케줄 실행 이력은 개별 삭제 대상이 아니다."""
        return self.type == "manual"
