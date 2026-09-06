"""BackgroundJobRepository: agent_background_job 저장소.

commit/rollback 호출 금지 — 트랜잭션 경계는 호출측(워커의 session_factory 블록
또는 get_session dependency)이 소유한다 (DB-001).

jobs-page-revamp: 소프트 삭제 도입 (Design §10.2). 이 테이블을 읽는 모든
쿼리는 `_active()` 를 거쳐 deleted_at 필터를 반드시 포함한다. 예외는 워커가
소유한 전이 경로(claim_queued/finish/reconcile_orphan_running) 뿐이며,
진행 중 작업은 삭제가 409 로 막히므로 삭제된 행이 그 경로에 들어올 수 없다.
"""
from datetime import datetime

from sqlalchemy import func, literal, null, select, union_all, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.background_job.entity import (
    BackgroundJob,
    JobHistoryItem,
    JobStatus,
)
from src.domain.background_job.interfaces import BackgroundJobRepositoryInterface
from src.domain.background_job.policies import JobQueuePolicy, JobTransitionPolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.agent_builder.models import AgentDefinitionModel
from src.infrastructure.agent_schedule.models import (
    AgentScheduleModel,
    AgentScheduleRunModel,
)
from src.infrastructure.background_job.models import AgentBackgroundJobModel

_ACTIVE_STATUSES = ("queued", "running")
_FINISHED_STATUSES = ("success", "failed")

# jobs-page-revamp Design §4.2 — 상태 그룹 필터 (FR-07)
_STATUS_GROUPS: dict[str, tuple[str, ...]] = {
    "all": (),
    "running": _ACTIVE_STATUSES,
    "done": _FINISHED_STATUSES,
}


def _active(*conditions):
    """활성 job 조건 — deleted_at 필터를 빠뜨릴 수 없게 감싼다 (Design §10.2)."""
    return (AgentBackgroundJobModel.deleted_at.is_(None), *conditions)


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
        deleted_at=model.deleted_at,
    )


def _status_filter(column, status_group: str):
    """상태 그룹 → WHERE 조건 (없으면 빈 튜플)."""
    if status_group not in _STATUS_GROUPS:
        raise ValueError(f"지원하지 않는 상태 필터입니다: {status_group}")
    statuses = _STATUS_GROUPS[status_group]
    return (column.in_(statuses),) if statuses else ()


def _manual_select(user_id: str, status_group: str, since_utc: datetime | None):
    """수동 job → 통합 이력 컬럼 (Design §4.3, 컬럼 순서 고정)."""
    job = AgentBackgroundJobModel
    conditions = _active(
        job.user_id == user_id,
        *_status_filter(job.status, status_group),
    )
    if since_utc is not None:
        conditions = (*conditions, job.queued_at >= since_utc)
    return (
        select(
            job.id.label("id"),
            literal("manual").label("type"),
            job.queued_at.label("occurred_at"),
            job.query.label("title"),
            job.status.label("status"),
            job.agent_id.label("agent_id"),
            AgentDefinitionModel.name.label("agent_name"),
            job.session_id.label("session_id"),
            job.error_message.label("error_message"),
            job.seen_at.label("seen_at"),
            job.started_at.label("started_at"),
            job.finished_at.label("finished_at"),
        )
        .outerjoin(AgentDefinitionModel, job.agent_id == AgentDefinitionModel.id)
        .where(*conditions)
    )


def _schedule_select(
    user_id: str, status_group: str, since_utc: datetime | None
):
    """스케줄 실행 → 통합 이력 컬럼. 소유자는 agent_schedule 경유로만 판정한다."""
    run = AgentScheduleRunModel
    conditions = (
        AgentScheduleModel.user_id == user_id,
        *_status_filter(run.status, status_group),
    )
    if since_utc is not None:
        conditions = (*conditions, run.scheduled_for >= since_utc)
    return (
        select(
            run.id.label("id"),
            literal("schedule").label("type"),
            run.scheduled_for.label("occurred_at"),
            AgentScheduleModel.name.label("title"),
            run.status.label("status"),
            run.agent_id.label("agent_id"),
            AgentDefinitionModel.name.label("agent_name"),
            run.session_id.label("session_id"),
            run.error_message.label("error_message"),
            null().label("seen_at"),  # 스케줄 실행은 확인(seen) 대상이 아니다
            run.started_at.label("started_at"),
            run.finished_at.label("finished_at"),
        )
        .join(AgentScheduleModel, run.schedule_id == AgentScheduleModel.id)
        .outerjoin(AgentDefinitionModel, run.agent_id == AgentDefinitionModel.id)
        .where(*conditions)
    )


def _to_history_item(row) -> JobHistoryItem:
    return JobHistoryItem(
        id=row.id,
        type=row.type,
        occurred_at=row.occurred_at,
        title=row.title,
        status=row.status,
        agent_id=row.agent_id,
        agent_name=row.agent_name,
        session_id=row.session_id,
        error_message=row.error_message,
        seen_at=row.seen_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
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
        # session.get() 은 삭제 필터를 걸 수 없어 select 로 조회한다 (Design §10.2)
        stmt = (
            select(AgentBackgroundJobModel)
            .where(*_active(AgentBackgroundJobModel.id == job_id))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        model = result.scalars().first()
        return _to_entity(model) if model is not None else None

    async def find_active_by_session(
        self, session_id: str, request_id: str
    ) -> BackgroundJob | None:
        stmt = (
            select(AgentBackgroundJobModel)
            .where(
                *_active(
                    AgentBackgroundJobModel.session_id == session_id,
                    AgentBackgroundJobModel.status.in_(_ACTIVE_STATUSES),
                )
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

    async def count_unseen(self, user_id: str, request_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(AgentBackgroundJobModel)
            .where(
                *_active(
                    AgentBackgroundJobModel.user_id == user_id,
                    AgentBackgroundJobModel.seen_at.is_(None),
                    AgentBackgroundJobModel.status.in_(_FINISHED_STATUSES),
                )
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
                *_active(
                    AgentBackgroundJobModel.id == job_id,
                    AgentBackgroundJobModel.user_id == user_id,
                )
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
                *_active(
                    AgentBackgroundJobModel.user_id == user_id,
                    AgentBackgroundJobModel.seen_at.is_(None),
                    AgentBackgroundJobModel.status.in_(_FINISHED_STATUSES),
                )
            )
            .values(seen_at=now_utc, updated_at=now_utc)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount or 0

    # ── jobs-page-revamp: 소프트 삭제 (Design §4.2) ──────────────────

    async def soft_delete(
        self, job_id: str, user_id: str, now_utc: datetime, request_id: str
    ) -> bool:
        stmt = (
            update(AgentBackgroundJobModel)
            .where(
                *_active(
                    AgentBackgroundJobModel.id == job_id,
                    AgentBackgroundJobModel.user_id == user_id,
                    # UseCase 의 상태 검사 이후 워커가 claim 했을 수 있다.
                    # 조건을 쿼리에도 걸어 진행 중 작업이 지워지지 않게 한다.
                    AgentBackgroundJobModel.status.in_(_FINISHED_STATUSES),
                )
            )
            .values(deleted_at=now_utc, updated_at=now_utc)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        deleted = (result.rowcount or 0) > 0
        if deleted:
            self._logger.info(
                "background job soft deleted",
                request_id=request_id,
                job_id=job_id,
            )
        return deleted

    async def soft_delete_completed(
        self, user_id: str, now_utc: datetime, request_id: str
    ) -> int:
        """완료된 작업 일괄 정리 (FR-05) — 진행 중 작업은 대상에서 제외한다."""
        stmt = (
            update(AgentBackgroundJobModel)
            .where(
                *_active(
                    AgentBackgroundJobModel.user_id == user_id,
                    AgentBackgroundJobModel.status.in_(_FINISHED_STATUSES),
                )
            )
            .values(deleted_at=now_utc, updated_at=now_utc)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        count = result.rowcount or 0
        self._logger.info(
            "background jobs cleaned up",
            request_id=request_id,
            count=count,
        )
        return count

    # ── jobs-page-revamp: 통합 이력 조회 (Design §4.3) ───────────────

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
        sub = self._history_subquery(
            user_id, status_group, history_type, since_utc
        )
        stmt = (
            select(sub)
            # 보조 정렬 키(id) 없이는 동시각 항목이 페이지 경계에서 흔들린다
            .order_by(sub.c.occurred_at.desc(), sub.c.id.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return [_to_history_item(row) for row in result.all()]

    async def count_history(
        self,
        user_id: str,
        *,
        status_group: str,
        history_type: str,
        since_utc: datetime | None,
        request_id: str,
    ) -> int:
        sub = self._history_subquery(
            user_id, status_group, history_type, since_utc
        )
        result = await self._session.execute(
            select(func.count()).select_from(sub)
        )
        return result.scalar_one()

    def _history_subquery(
        self,
        user_id: str,
        status_group: str,
        history_type: str,
        since_utc: datetime | None,
    ):
        """수동 job ∪ 스케줄 실행 — 컬럼 순서·개수를 맞춘 정규화 서브쿼리."""
        parts = []
        if history_type in ("all", "manual"):
            parts.append(_manual_select(user_id, status_group, since_utc))
        if history_type in ("all", "schedule"):
            parts.append(_schedule_select(user_id, status_group, since_utc))
        if not parts:
            raise ValueError(f"지원하지 않는 유형 필터입니다: {history_type}")
        if len(parts) == 1:
            return parts[0].subquery()
        return union_all(*parts).subquery()
