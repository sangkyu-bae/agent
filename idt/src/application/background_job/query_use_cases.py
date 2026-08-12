"""background-jobs 조회·확인 처리 use case 묶음 (Design §4-3).

전부 user_id 인가 — 본인 소유만. 타인 job 은 404 통일 (사유 비구분).
(여러 소형 UC 를 한 파일에 두는 선례: agent_webhook/manage_webhook_use_cases.py)
"""
from datetime import datetime, timezone

from src.application.background_job.errors import JobNotFoundError
from src.application.background_job.schemas import (
    JobResponse,
    SeenAllResponse,
    UnseenCountResponse,
)
from src.domain.background_job.interfaces import BackgroundJobRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ListJobsUseCase:
    def __init__(
        self, job_repo: BackgroundJobRepositoryInterface, logger: LoggerInterface
    ) -> None:
        self._job_repo = job_repo
        self._logger = logger

    async def execute(
        self,
        user_id: str,
        status: str | None,
        limit: int,
        offset: int,
        request_id: str,
    ) -> list[JobResponse]:
        rows = await self._job_repo.list_by_user(
            user_id, status, limit, offset, request_id
        )
        return [
            JobResponse.from_entity(job, agent_name) for job, agent_name in rows
        ]


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
        self, job_repo: BackgroundJobRepositoryInterface, logger: LoggerInterface
    ) -> None:
        self._job_repo = job_repo
        self._logger = logger

    async def execute(self, user_id: str, request_id: str) -> UnseenCountResponse:
        count = await self._job_repo.count_unseen(user_id, request_id)
        return UnseenCountResponse(count=count)


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
