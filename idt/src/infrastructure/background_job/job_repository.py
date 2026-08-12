"""BackgroundJobRepository: agent_background_job 저장소.

commit/rollback 호출 금지 — 트랜잭션 경계는 호출측(워커의 session_factory 블록
또는 get_session dependency)이 소유한다 (DB-001).
"""
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.background_job.entity import BackgroundJob, JobStatus
from src.domain.background_job.interfaces import BackgroundJobRepositoryInterface
from src.domain.background_job.policies import JobQueuePolicy, JobTransitionPolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.agent_builder.models import AgentDefinitionModel
from src.infrastructure.background_job.models import AgentBackgroundJobModel

_ACTIVE_STATUSES = ("queued", "running")
_FINISHED_STATUSES = ("success", "failed")


def _to_entity(model: AgentBackgroundJobModel) -> BackgroundJob:
    return BackgroundJob(
        id=model.id,
        user_id=model.user_id,
        agent_id=model.agent_id,
        source=model.source,
        query=model.query,
        session_id=model.session_id,
        run_id=model.run_id,
        status=model.status,
        error_message=model.error_message,
        seen_at=model.seen_at,
        queued_at=model.queued_at,
        started_at=model.started_at,
        finished_at=model.finished_at,
        request_id=model.request_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class BackgroundJobRepository(BackgroundJobRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def enqueue(self, job: BackgroundJob, request_id: str) -> None:
        self._session.add(
            AgentBackgroundJobModel(
                id=job.id,
                user_id=job.user_id,
                agent_id=job.agent_id,
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
                request_id=job.request_id,
                created_at=job.created_at,
                updated_at=job.updated_at,
            )
        )
        await self._session.flush()
        self._logger.info(
            "background job enqueued",
            request_id=request_id,
            job_id=job.id,
            agent_id=job.agent_id,
        )

    async def find_by_id(
        self, job_id: str, request_id: str
    ) -> BackgroundJob | None:
        model = await self._session.get(AgentBackgroundJobModel, job_id)
        return _to_entity(model) if model is not None else None

    async def find_active_by_session(
        self, session_id: str, request_id: str
    ) -> BackgroundJob | None:
        stmt = (
            select(AgentBackgroundJobModel)
            .where(
                AgentBackgroundJobModel.session_id == session_id,
                AgentBackgroundJobModel.status.in_(_ACTIVE_STATUSES),
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        model = result.scalars().first()
        return _to_entity(model) if model is not None else None

    async def claim_queued(
        self, limit: int, now_utc: datetime, request_id: str
    ) -> list[BackgroundJob]:
        """queued 선점 (Design D2) — claim_due 동형.

        FOR UPDATE SKIP LOCKED 로 잠긴 행을 건너뛰어 동시 claim 간 이중 선점을
        방지한다. running 전환까지 같은 트랜잭션 — commit 은 호출측이 담당.
        """
        stmt = (
            select(AgentBackgroundJobModel)
            .where(AgentBackgroundJobModel.status == "queued")
            .order_by(AgentBackgroundJobModel.queued_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        for model in models:
            model.status = "running"
            model.started_at = now_utc
            model.updated_at = now_utc
        await self._session.flush()
        if models:
            self._logger.info(
                "background jobs claimed",
                request_id=request_id,
                count=len(models),
            )
        return [_to_entity(m) for m in models]

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
        model = await self._session.get(AgentBackgroundJobModel, job_id)
        if model is None:
            raise ValueError(f"백그라운드 작업을 찾을 수 없습니다: {job_id}")
        if not JobTransitionPolicy.can_transition(model.status, status):
            # 종결 상태 재기록 시도(shutdown 마킹 vs 정상 완료 경합 등)는 무변경
            self._logger.warning(
                "background job transition denied",
                request_id=request_id,
                job_id=job_id,
                current=model.status,
                requested=status,
            )
            return False
        model.status = status
        model.finished_at = now_utc
        model.updated_at = now_utc
        if session_id is not None:
            model.session_id = session_id
        if run_id is not None:
            model.run_id = run_id
        model.error_message = JobQueuePolicy.truncate_error(error_message)
        await self._session.flush()
        self._logger.info(
            "background job finished",
            request_id=request_id,
            job_id=job_id,
            status=status,
        )
        return True

    async def reconcile_orphan_running(
        self, error_message: str, now_utc: datetime, request_id: str
    ) -> int:
        stmt = (
            update(AgentBackgroundJobModel)
            .where(AgentBackgroundJobModel.status == "running")
            .values(
                status="failed",
                error_message=JobQueuePolicy.truncate_error(error_message),
                finished_at=now_utc,
                updated_at=now_utc,
            )
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        count = result.rowcount or 0
        if count:
            self._logger.warning(
                "background jobs reconciled (orphan running → failed)",
                request_id=request_id,
                count=count,
            )
        return count

    async def list_by_user(
        self,
        user_id: str,
        status: str | None,
        limit: int,
        offset: int,
        request_id: str,
    ) -> list[tuple[BackgroundJob, str | None]]:
        stmt = (
            select(AgentBackgroundJobModel, AgentDefinitionModel.name)
            .outerjoin(
                AgentDefinitionModel,
                AgentBackgroundJobModel.agent_id == AgentDefinitionModel.id,
            )
            .where(AgentBackgroundJobModel.user_id == user_id)
        )
        if status is not None:
            stmt = stmt.where(AgentBackgroundJobModel.status == status)
        stmt = (
            stmt.order_by(AgentBackgroundJobModel.queued_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return [(_to_entity(m), name) for m, name in result.all()]

    async def count_unseen(self, user_id: str, request_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(AgentBackgroundJobModel)
            .where(
                AgentBackgroundJobModel.user_id == user_id,
                AgentBackgroundJobModel.seen_at.is_(None),
                AgentBackgroundJobModel.status.in_(_FINISHED_STATUSES),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def mark_seen(
        self, job_id: str, user_id: str, now_utc: datetime, request_id: str
    ) -> bool:
        stmt = (
            update(AgentBackgroundJobModel)
            .where(
                AgentBackgroundJobModel.id == job_id,
                AgentBackgroundJobModel.user_id == user_id,
            )
            .values(seen_at=now_utc, updated_at=now_utc)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return (result.rowcount or 0) > 0

    async def mark_all_seen(
        self, user_id: str, now_utc: datetime, request_id: str
    ) -> int:
        stmt = (
            update(AgentBackgroundJobModel)
            .where(
                AgentBackgroundJobModel.user_id == user_id,
                AgentBackgroundJobModel.seen_at.is_(None),
                AgentBackgroundJobModel.status.in_(_FINISHED_STATUSES),
            )
            .values(seen_at=now_utc, updated_at=now_utc)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount or 0
