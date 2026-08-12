"""EnqueueJobUseCase: 백그라운드 작업 등록 (Design §4-3, D5·D10).

세션에는 아무것도 저장하지 않는다 — user 메시지는 실행 시점에
RunAgentUseCase 가 단일 저장한다 (중복 방지, D10).
"""
import uuid
from datetime import datetime, timezone

from src.application.background_job.errors import (
    JobConflictError,
    JobNotFoundError,
)
from src.application.background_job.schemas import (
    EnqueueJobRequest,
    EnqueueJobResponse,
)
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_builder.policies import AccessCheckInput, VisibilityPolicy
from src.domain.background_job.entity import BackgroundJob
from src.domain.background_job.interfaces import BackgroundJobRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class EnqueueJobUseCase:
    def __init__(
        self,
        job_repo: BackgroundJobRepositoryInterface,
        agent_repo: AgentDefinitionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._job_repo = job_repo
        self._agent_repo = agent_repo
        self._logger = logger

    async def execute(
        self,
        agent_id: str,
        request: EnqueueJobRequest,
        user_id: str,
        department_ids: list[str],
        request_id: str,
    ) -> EnqueueJobResponse:
        await self._verify_agent_access(
            agent_id, user_id, department_ids, request_id
        )
        await self._verify_no_active_in_session(request.session_id, request_id)

        now = _utc_now()
        job = BackgroundJob(
            id=str(uuid.uuid4()),
            user_id=user_id,
            agent_id=agent_id,
            source=request.source,
            query=request.query,
            session_id=request.session_id,
            run_id=None,
            status="queued",
            error_message=None,
            seen_at=None,
            queued_at=now,
            started_at=None,
            finished_at=None,
            request_id=request_id,
            created_at=now,
            updated_at=now,
        )
        await self._job_repo.enqueue(job, request_id)
        self._logger.info(
            "background job accepted",
            request_id=request_id,
            job_id=job.id,
            agent_id=agent_id,
        )
        return EnqueueJobResponse(
            job_id=job.id, status=job.status, request_id=request_id
        )

    async def _verify_agent_access(
        self,
        agent_id: str,
        user_id: str,
        department_ids: list[str],
        request_id: str,
    ) -> None:
        """run_agent 가시성 검사 동형 — 미존재·비가시 모두 404 (사유 비구분)."""
        agent = await self._agent_repo.find_by_id(agent_id, request_id)
        if agent is None:
            raise JobNotFoundError("에이전트를 찾을 수 없습니다")
        check = AccessCheckInput(
            agent_owner_id=agent.user_id,
            agent_visibility=agent.visibility,
            agent_department_id=agent.department_id,
            viewer_user_id=user_id,
            viewer_department_ids=department_ids,
            viewer_role="user",
        )
        if not VisibilityPolicy.can_access(check):
            raise JobNotFoundError("에이전트를 찾을 수 없습니다")

    async def _verify_no_active_in_session(
        self, session_id: str | None, request_id: str
    ) -> None:
        if session_id is None:
            return
        active = await self._job_repo.find_active_by_session(
            session_id, request_id
        )
        if active is not None:
            raise JobConflictError(
                "이 대화에는 이미 진행 중인 백그라운드 작업이 있습니다"
            )
