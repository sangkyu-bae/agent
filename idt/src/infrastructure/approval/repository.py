"""ApprovalRepository — approval_request 영속 어댑터.

Design Ref: §2.3, §3.3.

DB-001: 내부에서 commit()/rollback() 을 호출하지 않는다 — 트랜잭션 경계는
호출측 UseCase 가 소유한다. flush() 까지만 수행한다.
"""
from datetime import datetime, timezone

from sqlalchemy import func, select, update

from src.domain.approval.entity import (
    ApprovalRequest,
    ApprovalStatus,
    ResumeSnapshot,
)
from src.domain.approval.interfaces import ApprovalRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.approval.models import ApprovalRequestModel

# 런당 활성 pending 1건 불변식(FR-06) 판정에 쓰는 비종료 상태 집합
_ACTIVE_STATUSES = ("pending", "approved", "scheduled")


def _utcnow() -> datetime:
    """UTC naive 현재 시각.

    datetime.utcnow() 는 3.12 에서 deprecated 다. 컬럼이 naive DATETIME
    (agent_schedule 관례) 이므로 tzinfo 를 떼어 맞춘다.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ApprovalRepository(ApprovalRepositoryInterface):
    def __init__(self, session, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def create(self, request: ApprovalRequest, request_id: str) -> None:
        self._session.add(_to_model(request))
        await self._session.flush()
        self._logger.info(
            "approval request created",
            request_id=request_id,
            approval_id=request.id,
            run_id=request.run_id,
            tool_id=request.tool_id,
        )

    async def find(
        self, approval_id: str, request_id: str
    ) -> ApprovalRequest | None:
        result = await self._session.execute(
            select(ApprovalRequestModel).where(
                ApprovalRequestModel.id == approval_id
            )
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None

    async def find_active_by_run(
        self, run_id: str, request_id: str
    ) -> ApprovalRequest | None:
        result = await self._session.execute(
            select(ApprovalRequestModel)
            .where(
                ApprovalRequestModel.run_id == run_id,
                ApprovalRequestModel.status.in_(_ACTIVE_STATUSES),
            )
            .limit(1)
        )
        model = result.scalar_one_or_none()
        return _to_entity(model) if model else None

    async def list_for_user(
        self,
        agent_ids: tuple[str, ...],
        request_id: str,
        *,
        statuses: tuple[ApprovalStatus, ...],
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[ApprovalRequest], int]:
        """소유 에이전트 id 목록으로 범위를 좁혀 조회한다.

        agent_definition 을 서브쿼리로 참조하지 않는 이유: 다른 애그리게이트의
        ORM 모델을 끌어오면 공유 Base.metadata 에 그 테이블과 연쇄 FK 가
        등록되어, sqlite 로 create_all 하는 통합 테스트들이 무너진다(측정 91건).
        소유 판정은 UseCase 가 agent 리포지토리로 해결해 id 만 넘긴다.
        """
        if not agent_ids:
            return [], 0
        base = select(ApprovalRequestModel).where(
            ApprovalRequestModel.agent_id.in_(agent_ids),
            ApprovalRequestModel.status.in_(statuses),
        )
        total_result = await self._session.execute(
            select(func.count()).select_from(base.subquery())
        )
        rows_result = await self._session.execute(
            base.order_by(ApprovalRequestModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        models = rows_result.scalars().all()
        return [_to_entity(m) for m in models], int(total_result.scalar() or 0)

    async def count_unseen(
        self, agent_ids: tuple[str, ...], request_id: str
    ) -> int:
        if not agent_ids:
            return 0
        result = await self._session.execute(
            select(func.count())
            .select_from(ApprovalRequestModel)
            .where(
                ApprovalRequestModel.agent_id.in_(agent_ids),
                ApprovalRequestModel.seen_at.is_(None),
                ApprovalRequestModel.status.in_(_ACTIVE_STATUSES),
            )
        )
        return int(result.scalar() or 0)

    async def compare_and_set_status(
        self,
        approval_id: str,
        *,
        expected: ApprovalStatus,
        new_status: ApprovalStatus,
        request_id: str,
        decided_by: str | None = None,
        decided_at: datetime | None = None,
        decision_reason: str | None = None,
        execute_after: datetime | None = None,
        executed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> bool:
        """조건부 UPDATE — 이중 집행 방어 2차 저지선.

        read-then-write 대신 `WHERE status = expected` 한 문장에 맡긴다.
        승인 버튼 2회 클릭이 동시에 들어와도 두 번째는 영향 행 0 이 된다.
        """
        values = _changed_values(
            new_status=new_status,
            decided_by=decided_by,
            decided_at=decided_at,
            decision_reason=decision_reason,
            execute_after=execute_after,
            executed_at=executed_at,
            error_message=error_message,
        )
        result = await self._session.execute(
            update(ApprovalRequestModel)
            .where(
                ApprovalRequestModel.id == approval_id,
                ApprovalRequestModel.status == expected,
            )
            .values(**values)
        )
        changed = (result.rowcount or 0) > 0
        self._logger.info(
            "approval status transition",
            request_id=request_id,
            approval_id=approval_id,
            expected=expected,
            new_status=new_status,
            applied=changed,
        )
        return changed

    async def claim_due(
        self, now_utc: datetime, request_id: str, *, limit: int = 50
    ) -> list[ApprovalRequest]:
        """집행 시각이 도래한 scheduled 건 선점.

        agent_schedule.claim_due 와 동일하게 FOR UPDATE SKIP LOCKED 로 잠긴
        행을 건너뛴다 — 다중 tick 워커의 이중 집행 방어 3차 저지선.
        여기서는 상태를 바꾸지 않는다: 집행 성패에 따라 executed/failed 가
        갈리므로 전이는 UseCase 가 compare_and_set_status 로 수행한다.
        """
        result = await self._session.execute(
            select(ApprovalRequestModel)
            .where(
                ApprovalRequestModel.status == "scheduled",
                ApprovalRequestModel.execute_after.is_not(None),
                ApprovalRequestModel.execute_after <= now_utc,
                ApprovalRequestModel.expires_at > now_utc,
            )
            .order_by(ApprovalRequestModel.execute_after)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        models = result.scalars().all()
        self._logger.info(
            "approvals claimed", request_id=request_id, count=len(models)
        )
        return [_to_entity(m) for m in models]

    async def mark_seen(
        self, approval_id: str, agent_ids: tuple[str, ...], request_id: str
    ) -> None:
        """Check G7 — agent_id 범위를 WHERE 에 넣어 타인 건을 건드리지 못하게 한다."""
        if not agent_ids:
            return
        await self._session.execute(
            update(ApprovalRequestModel)
            .where(
                ApprovalRequestModel.id == approval_id,
                ApprovalRequestModel.agent_id.in_(agent_ids),
                ApprovalRequestModel.seen_at.is_(None),
            )
            .values(seen_at=_utcnow(), updated_at=_utcnow())
        )

    async def expire_overdue(self, now_utc: datetime, request_id: str) -> int:
        """만료 경과 건 일괄 전이. 이미 종료된 건은 건드리지 않는다."""
        result = await self._session.execute(
            update(ApprovalRequestModel)
            .where(
                ApprovalRequestModel.status.in_(("pending", "scheduled")),
                ApprovalRequestModel.expires_at <= now_utc,
            )
            .values(status="expired", updated_at=now_utc)
        )
        count = result.rowcount or 0
        if count:
            self._logger.info(
                "approvals expired", request_id=request_id, count=count
            )
        return count

def _changed_values(*, new_status: str, **optional) -> dict:
    """None 인 선택 필드는 SET 절에서 제외한다 — 기존 값을 지우지 않기 위함."""
    values: dict = {"status": new_status, "updated_at": _utcnow()}
    values.update({k: v for k, v in optional.items() if v is not None})
    return values


def _to_model(entity: ApprovalRequest) -> ApprovalRequestModel:
    return ApprovalRequestModel(
        id=entity.id,
        run_id=entity.run_id,
        agent_id=entity.agent_id,
        requested_by=entity.requested_by,
        worker_id=entity.worker_id,
        tool_id=entity.tool_id,
        tool_args=entity.tool_args,
        draft=entity.draft,
        status=entity.status,
        idempotency_key=entity.idempotency_key,
        snapshot_version=entity.snapshot.schema_version,
        agent_updated_at=entity.snapshot.agent_updated_at,
        resume_snapshot=entity.snapshot.state_json,
        execute_after=entity.execute_after,
        expires_at=entity.expires_at,
        decided_by=entity.decided_by,
        decided_at=entity.decided_at,
        decision_reason=entity.decision_reason,
        executed_at=entity.executed_at,
        error_message=entity.error_message,
        seen_at=entity.seen_at,
        session_id=entity.session_id,
        request_id=entity.request_id,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def _to_entity(model: ApprovalRequestModel) -> ApprovalRequest:
    return ApprovalRequest(
        id=model.id,
        run_id=model.run_id,
        agent_id=model.agent_id,
        requested_by=model.requested_by,
        worker_id=model.worker_id,
        tool_id=model.tool_id,
        tool_args=model.tool_args or {},
        draft=model.draft,
        status=model.status,
        idempotency_key=model.idempotency_key,
        snapshot=ResumeSnapshot(
            schema_version=model.snapshot_version,
            agent_updated_at=model.agent_updated_at,
            worker_id=model.worker_id,
            state_json=model.resume_snapshot,
        ),
        expires_at=model.expires_at,
        request_id=model.request_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        execute_after=model.execute_after,
        decided_by=model.decided_by,
        decided_at=model.decided_at,
        decision_reason=model.decision_reason,
        executed_at=model.executed_at,
        error_message=model.error_message,
        seen_at=model.seen_at,
        session_id=model.session_id,
    )
