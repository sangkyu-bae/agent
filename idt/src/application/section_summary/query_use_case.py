"""SectionSummaryQueryUseCase — 잡 상태 조회/재시도 (Design §7.2/§7.3, D15).

per-request 인스턴스: KB 권한(can_read/can_write)을 요청 세션으로 검증하고,
재시도 킥오프는 싱글턴 런처에 위임한다.
"""
from datetime import datetime

from src.application.section_summary.launcher import SectionSummaryLauncher
from src.application.section_summary.schemas import (
    SectionSummaryJobStatus,
    SectionSummaryRetryNotAllowedError,
)
from src.domain.auth.entities import User
from src.domain.department.interfaces import DepartmentRepositoryInterface
from src.domain.knowledge_base.interfaces import (
    KnowledgeBaseRepositoryInterface,
)
from src.domain.knowledge_base.policy import KnowledgeBasePolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.section_summary.entities import (
    JOB_STATUS_PROCESSING,
    SectionSummaryJob,
)
from src.domain.section_summary.policy import SectionSummaryJobPolicy
from src.infrastructure.section_summary.job_repository import (
    SectionSummaryJobRepository,
)


class SectionSummaryQueryUseCase:
    def __init__(
        self,
        kb_repo: KnowledgeBaseRepositoryInterface,
        dept_repo: DepartmentRepositoryInterface,
        kb_policy: KnowledgeBasePolicy,
        job_repo: SectionSummaryJobRepository,
        policy: SectionSummaryJobPolicy,
        launcher: SectionSummaryLauncher,
        logger: LoggerInterface,
        stale_seconds: int,
    ) -> None:
        self._kb_repo = kb_repo
        self._dept_repo = dept_repo
        self._kb_policy = kb_policy
        self._job_repo = job_repo
        self._policy = policy
        self._launcher = launcher
        self._logger = logger
        self._stale_seconds = stale_seconds

    async def get_status(
        self, kb_id: str, document_id: str, user: User, request_id: str
    ) -> SectionSummaryJobStatus:
        await self._check_access(kb_id, user, request_id, write=False)
        job = await self._require_job(kb_id, document_id, request_id)
        return self._to_status(job)

    async def retry(
        self, kb_id: str, document_id: str, user: User, request_id: str
    ) -> SectionSummaryJobStatus:
        await self._check_access(kb_id, user, request_id, write=True)
        job = await self._require_job(kb_id, document_id, request_id)
        if not self._policy.can_retry(
            job, datetime.now(), self._stale_seconds
        ):
            raise SectionSummaryRetryNotAllowedError(
                f"job in status '{job.status}' cannot be retried"
            )
        await self._launcher.retry(job.id, request_id)
        self._logger.info(
            "Section summary retry requested",
            request_id=request_id,
            job_id=job.id,
            document_id=document_id,
        )
        return self._to_status(job, status_override=JOB_STATUS_PROCESSING)

    async def _check_access(
        self, kb_id: str, user: User, request_id: str, write: bool
    ) -> None:
        kb = await self._kb_repo.find_by_id(kb_id, request_id)
        if kb is None:
            raise ValueError(f"Knowledge base '{kb_id}' not found")
        dept_ids = await self._get_dept_ids(user, request_id)
        allowed = (
            self._kb_policy.can_write(user, kb, dept_ids)
            if write
            else self._kb_policy.can_read(user, kb, dept_ids)
        )
        if not allowed:
            action = "write" if write else "read"
            raise PermissionError(
                f"No {action} access to knowledge base '{kb_id}'"
            )

    async def _require_job(
        self, kb_id: str, document_id: str, request_id: str
    ) -> SectionSummaryJob:
        job = await self._job_repo.find_by_document(document_id, request_id)
        if job is None or job.kb_id != kb_id:
            raise ValueError(
                f"Section summary job for document '{document_id}' not found"
            )
        return job

    async def _get_dept_ids(self, user: User, request_id: str) -> list[str]:
        if user.id is None:
            return []
        depts = await self._dept_repo.find_departments_by_user(
            user.id, request_id
        )
        return [d.department_id for d in depts]

    def _to_status(
        self, job: SectionSummaryJob, status_override: str | None = None
    ) -> SectionSummaryJobStatus:
        return SectionSummaryJobStatus(
            job_id=job.id,
            document_id=job.document_id,
            status=status_override or job.status,
            total_sections=job.total_sections,
            done_sections=job.done_sections,
            failed_sections=job.failed_sections,
            is_stale=self._policy.is_stale(
                job, datetime.now(), self._stale_seconds
            ),
            error=job.error,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
