"""background-jobs 조회·확인 처리 use case 묶음 (Design §4-3).

전부 user_id 인가 — 본인 소유만. 타인 job 은 404 통일 (사유 비구분).
(여러 소형 UC 를 한 파일에 두는 선례: agent_webhook/manage_webhook_use_cases.py)
"""
from datetime import datetime, timezone

from src.application.background_job.errors import JobNotFoundError
from src.application.background_job.period import period_to_utc_start
from src.application.background_job.schemas import (
    JobHistoryResponse,
    JobListResponse,
    JobResponse,
    SeenAllResponse,
    UnseenCountResponse,
)
from src.domain.background_job.interfaces import BackgroundJobRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ListJobHistoryUseCase:
    """작업 기록 — 수동 job + 스케줄 실행 통합 목록 (jobs-page-revamp §4.2).

    Design Ref: §2.0 Option C — 정렬·페이징·총건수는 전부 DB 가 계산한다.
    """

    def __init__(
        self, job_repo: BackgroundJobRepositoryInterface, logger: LoggerInterface
    ) -> None:
        self._job_repo = job_repo
        self._logger = logger

    async def execute(
        self,
        user_id: str,
        status_group: str,
        history_type: str,
        period: str,
        limit: int,
        offset: int,
        request_id: str,
    ) -> JobListResponse:
        # Plan SC: FR-09 — KST 경계를 UTC naive 로 환산해 DB 값과 비교
        since_utc = period_to_utc_start(period, _utc_now())
        filters = dict(
            status_group=status_group,
            history_type=history_type,
            since_utc=since_utc,
        )
        items = await self._job_repo.list_history(
            user_id, limit=limit, offset=offset, request_id=request_id, **filters
        )
        total = await self._job_repo.count_history(
            user_id, request_id=request_id, **filters
        )
        return JobListResponse(
            items=[JobHistoryResponse.from_item(i) for i in items], total=total
        )


class GetJobUseCase:
    def __init__(
        self, job_repo: BackgroundJobRepositoryInterface, logger: LoggerInterface
    ) -> None:
        self._job_repo = job_repo
        self._logger = logger

    async def execute(
        self, job_id: str, user_id: str, request_id: str
    ) -> JobResponse:
        job = await self._job_repo.find_by_id(job_id, request_id)
        if job is None or job.user_id != user_id:
            raise JobNotFoundError("작업을 찾을 수 없습니다")
        return JobResponse.from_entity(job)


class CountUnseenUseCase:
    def __init__(
        self,
        job_repo: BackgroundJobRepositoryInterface,
        logger: LoggerInterface,
        # approval-gate Design §5.5: 승인 대기 건수 합산 (미주입 시 0 — 무회귀).
        approval_counter=None,
    ) -> None:
        self._job_repo = job_repo
        self._logger = logger
        self._approval_counter = approval_counter

    async def execute(self, user_id: str, request_id: str) -> UnseenCountResponse:
        jobs = await self._job_repo.count_unseen(user_id, request_id)
        approvals = await self._count_approvals(user_id, request_id)
        # count 는 총합 — 기존 소비자의 의미를 바꾸지 않는다.
        return UnseenCountResponse(
            count=jobs + approvals, jobs=jobs, approvals=approvals
        )

    async def _count_approvals(self, user_id: str, request_id: str) -> int:
        """승인 대기 집계 실패가 벨 배지 전체를 죽이지 않게 한다."""
        if self._approval_counter is None:
            return 0
        try:
            return await self._approval_counter.count_unseen(
                user_id=user_id, request_id=request_id
            )
        except Exception as e:
            self._logger.warning(
                "approval unseen count failed — treated as 0",
                request_id=request_id, exception=e,
            )
            return 0


class MarkSeenUseCase:
    def __init__(
        self, job_repo: BackgroundJobRepositoryInterface, logger: LoggerInterface
    ) -> None:
        self._job_repo = job_repo
        self._logger = logger

    async def execute(self, job_id: str, user_id: str, request_id: str) -> None:
        ok = await self._job_repo.mark_seen(
            job_id, user_id, _utc_now(), request_id
        )
        if not ok:
            raise JobNotFoundError("작업을 찾을 수 없습니다")


class MarkAllSeenUseCase:
    def __init__(
        self, job_repo: BackgroundJobRepositoryInterface, logger: LoggerInterface
    ) -> None:
        self._job_repo = job_repo
        self._logger = logger

    async def execute(self, user_id: str, request_id: str) -> SeenAllResponse:
        updated = await self._job_repo.mark_all_seen(
            user_id, _utc_now(), request_id
        )
        return SeenAllResponse(updated=updated)
