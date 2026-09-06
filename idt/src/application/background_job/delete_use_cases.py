"""작업 소프트 삭제·정리 use case (jobs-page-revamp Design §4.2).

Design Ref: §4.2 — 물리 삭제 대신 deleted_at 을 찍어 run_id 관측 추적과
감사 이력을 보존한다. 사용자 관점에서는 삭제와 구분되지 않는다.
"""
from datetime import datetime, timezone

from src.application.background_job.errors import (
    JobDeleteConflictError,
    JobNotFoundError,
)
from src.application.background_job.schemas import CleanupJobsResponse
from src.domain.background_job.interfaces import BackgroundJobRepositoryInterface
from src.domain.background_job.policies import JobDeletionPolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface


def _utc_now() -> datetime:
    """DB 는 UTC naive 저장 — tzinfo 를 떼고 반환한다 (query_use_cases 동형)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DeleteJobUseCase:
    def __init__(
        self,
        job_repo: BackgroundJobRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._job_repo = job_repo
        self._logger = logger

    async def execute(self, job_id: str, user_id: str, request_id: str) -> None:
        """Plan SC: FR-03·FR-04 — 타인·미존재는 404, 진행 중은 409."""
        job = await self._job_repo.find_by_id(job_id, request_id)
        if job is None or job.user_id != user_id:
            # 사유를 구분하지 않는다 (타인 자원의 존재 여부 노출 금지)
            raise JobNotFoundError(f"작업을 찾을 수 없습니다: {job_id}")
        if not JobDeletionPolicy.can_delete(job.status):
            raise JobDeleteConflictError("진행 중인 작업은 삭제할 수 없습니다")

        deleted = await self._job_repo.soft_delete(
            job_id, user_id, _utc_now(), request_id
        )
        if not deleted:
            # find 이후 동시 삭제된 경우 — 목록에서 사라진 자원이므로 404
            raise JobNotFoundError(f"작업을 찾을 수 없습니다: {job_id}")


class CleanupJobsUseCase:
    def __init__(
        self,
        job_repo: BackgroundJobRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._job_repo = job_repo
        self._logger = logger

    async def execute(
        self, user_id: str, request_id: str
    ) -> CleanupJobsResponse:
        """Plan SC: FR-05 — 완료(success|failed) 작업만 일괄 정리."""
        count = await self._job_repo.soft_delete_completed(
            user_id, _utc_now(), request_id
        )
        return CleanupJobsResponse(deleted=count)
