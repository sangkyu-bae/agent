"""background-jobs 도메인 인터페이스 (Repository 포트)."""
from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.background_job.entity import (
    BackgroundJob,
    JobHistoryItem,
    JobStatus,
)


class BackgroundJobRepositoryInterface(ABC):
    @abstractmethod
    async def enqueue(self, job: BackgroundJob, request_id: str) -> None: ...

    @abstractmethod
    async def find_by_id(
        self, job_id: str, request_id: str
    ) -> BackgroundJob | None: ...

    @abstractmethod
    async def find_active_by_session(
        self, session_id: str, request_id: str
    ) -> BackgroundJob | None:
        """세션에 queued|running 상태 job 존재 확인 (D5 중복 가드)."""
        ...

    @abstractmethod
    async def claim_queued(
        self, limit: int, now_utc: datetime, request_id: str
    ) -> list[BackgroundJob]:
        """queued 선점: FOR UPDATE SKIP LOCKED + running 전환 (트랜잭션은 호출측, D2)."""
        ...

    @abstractmethod
    async def finish(
        self,
        job_id: str,
        status: JobStatus,
        now_utc: datetime,
        request_id: str,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        error_message: str | None = None,
    ) -> bool:
        """종료 기록. 전이 불허(이미 종결 등) 시 무변경 False."""
        ...

    @abstractmethod
    async def reconcile_orphan_running(
        self, error_message: str, now_utc: datetime, request_id: str
    ) -> int:
        """기동 시 고아 running → failed 일괄 정리 (D6). 처리 건수 반환."""
        ...

    # ── jobs-page-revamp: 통합 이력 조회 + 소프트 삭제 (Design §4.3) ──

    @abstractmethod
    async def list_history(
        self,
        user_id: str,
        *,
        status_group: str,
        history_type: str,
        since_utc: datetime | None,
        limit: int,
        offset: int,
        request_id: str,
    ) -> list[JobHistoryItem]:
        """수동 job + 스케줄 실행 통합 목록 (occurred_at DESC, id ASC)."""
        ...

    @abstractmethod
    async def count_history(
        self,
        user_id: str,
        *,
        status_group: str,
        history_type: str,
        since_utc: datetime | None,
        request_id: str,
    ) -> int:
        """list_history 와 동일 조건의 총건수 (페이지네이션용)."""
        ...

    @abstractmethod
    async def soft_delete(
        self, job_id: str, user_id: str, now_utc: datetime, request_id: str
    ) -> bool:
        """본인 소유 활성 job 소프트 삭제. 미존재/타인/이미 삭제면 False."""
        ...

    @abstractmethod
    async def soft_delete_completed(
        self, user_id: str, now_utc: datetime, request_id: str
    ) -> int:
        """본인 소유 success|failed job 일괄 소프트 삭제. 처리 건수 반환."""
        ...

    @abstractmethod
    async def count_unseen(self, user_id: str, request_id: str) -> int:
        """success|failed & seen_at IS NULL 건수 (벨 배지, D11)."""
        ...

    @abstractmethod
    async def mark_seen(
        self, job_id: str, user_id: str, now_utc: datetime, request_id: str
    ) -> bool:
        """본인 소유 job 확인 처리. 미존재/타인 소유면 False."""
        ...

    @abstractmethod
    async def mark_all_seen(
        self, user_id: str, now_utc: datetime, request_id: str
    ) -> int: ...
