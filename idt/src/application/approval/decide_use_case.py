"""DecideApprovalUseCase: 승인 / 거절.

Design Ref: §2.1 (승인 흐름), §2.2 (상태 기계), §6 (에러).

승인은 "집행 허가" 일 뿐이다 — 실제 집행 시각은 게이트 설정의 `execute_after`
가 정한다. cron 이 없으면 즉시 집행하고, 있으면 `scheduled` 로 두어
ExecuteDueApprovalsUseCase 가 그 시각에 집행한다.

이중 집행 방어: 모든 전이를 `compare_and_set_status`(조건부 UPDATE)로 하고,
영향 행이 0 이면 즉시 중단한다. 승인 버튼 2회 클릭의 두 번째는 여기서 막힌다.
"""
from datetime import datetime
from typing import Callable

from src.application.approval.errors import (  # noqa: F401 (라우터 재수출)
    ApprovalAgentChangedError,
    ApprovalConflictError,
    ApprovalError,
    ApprovalExpiredError,
    ApprovalForbiddenError,
    ApprovalInvalidWindowError,
    ApprovalNotFoundError,
)
from src.domain.approval.entity import ApprovalRequest, GateSettings
from src.domain.approval.interfaces import ApprovalRepositoryInterface
from src.domain.approval.policies import ApprovalPolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class DecideApprovalUseCase:
    def __init__(
        self,
        approval_repo: ApprovalRepositoryInterface,
        agent_repo,
        executor,
        gate_config_reader,
        logger: LoggerInterface,
        clock: Callable[[], datetime] | None = None,
        # approval-gate Design §2.1: 집행·거절 후 런 재개 (미주입 시 생략).
        resumer=None,
    ) -> None:
        self._repo = approval_repo
        self._agent_repo = agent_repo
        self._executor = executor
        self._gate_config_reader = gate_config_reader
        self._resumer = resumer
        self._logger = logger
        # 시계 주입 — 테스트가 예약 시각 계산을 결정적으로 검증할 수 있게 한다.
        self._now = clock or _utcnow

    async def get(
        self, approval_id: str, *, user_id: str, request_id: str
    ) -> tuple[ApprovalRequest, str | None]:
        """상세 조회 — 권한만 확인하고 상태·만료는 따지지 않는다.

        이미 처리·만료된 건도 이력으로 열람할 수 있어야 한다.
        에이전트명을 함께 돌려준다 (Check G6 — 권한 확인에서 이미 조회한 값).
        """
        approval = await self._repo.find(approval_id, request_id)
        if approval is None:
            raise ApprovalNotFoundError(approval_id)
        agent = await self._agent_repo.find_by_id(approval.agent_id, request_id)
        owner = getattr(agent, "user_id", "") if agent is not None else ""
        if not ApprovalPolicy.can_decide(user_id=user_id, agent_owner_id=owner):
            raise ApprovalForbiddenError(approval_id)
        return approval, getattr(agent, "name", None)

    async def approve(
        self,
        approval_id: str,
        *,
        user_id: str,
        request_id: str,
        execute_only: bool = False,
    ) -> ApprovalRequest:
        approval, agent = await self._load_and_authorize(
            approval_id, user_id, request_id, execute_only=execute_only
        )
        gate = await self._resolve_gate(approval, request_id)
        now = self._now()
        # Check G13: cron 은 게이트 설정의 타임존(기본 KST) 기준으로 해석한다.
        execute_after = ApprovalPolicy.next_execute_after(
            gate.execute_after, now_utc=now, tz=gate.timezone
        )
        # FR-26: 집행 예정이 만료보다 늦으면 승인해도 아무 일도 일어나지 않는다.
        # 침묵 실패 대신 승인 시점에 되돌려준다.
        try:
            ApprovalPolicy.validate_window(
                execute_after=execute_after, expires_at=approval.expires_at
            )
        except ValueError as e:
            raise ApprovalInvalidWindowError(str(e)) from e

        await self._transition(
            approval_id, expected="pending", event="approve", request_id=request_id,
            decided_by=user_id, decided_at=now,
        )
        if execute_after is not None and not execute_only:
            return await self._schedule(approval, execute_after, request_id)
        return await self._execute_now(approval, request_id)

    async def reject(
        self, approval_id: str, *, user_id: str, reason: str, request_id: str
    ) -> ApprovalRequest:
        if not (reason or "").strip():
            raise ValueError("reject requires a non-empty reason")
        approval, _ = await self._load_and_authorize(approval_id, user_id, request_id)
        await self._transition(
            approval_id, expected="pending", event="reject", request_id=request_id,
            decided_by=user_id, decided_at=self._now(), decision_reason=reason.strip(),
        )
        approval.status = "rejected"
        approval.decision_reason = reason.strip()
        # 거절도 승인과 같은 메커니즘으로 재개한다 — supervisor 관점에선
        # 둘 다 "워커가 이런 결과를 냈다" 이고, 사유를 받은 에이전트가
        # 대안을 찾거나 사유를 담아 마무리할 수 있다 (FR-12).
        await self._resume(
            approval, f"이 작업은 거절되었습니다(사유: {reason.strip()}).", request_id
        )
        return approval

    # ── 내부 ────────────────────────────────────────────────────────────

    async def _load_and_authorize(
        self, approval_id: str, user_id: str, request_id: str,
        *, execute_only: bool = False,
    ):
        approval = await self._repo.find(approval_id, request_id)
        if approval is None:
            raise ApprovalNotFoundError(approval_id)
        agent = await self._agent_repo.find_by_id(approval.agent_id, request_id)
        owner = getattr(agent, "user_id", "") if agent is not None else ""
        if not ApprovalPolicy.can_decide(user_id=user_id, agent_owner_id=owner):
            raise ApprovalForbiddenError(approval_id)
        if ApprovalPolicy.is_expired(approval.expires_at, now=self._now()):
            raise ApprovalExpiredError(approval_id)
        if approval.status != "pending":
            raise ApprovalConflictError(f"status={approval.status}")
        # FR-14: 정의가 바뀌면 스냅샷 재개가 이상 동작한다. execute_only 는
        # 재개를 포기하고 집행만 하겠다는 사용자의 명시적 선택이므로 통과.
        if not execute_only and _agent_changed(agent, approval):
            raise ApprovalAgentChangedError(approval_id)
        return approval, agent

    async def _resolve_gate(
        self, approval: ApprovalRequest, request_id: str
    ) -> GateSettings:
        config = await self._gate_config_reader.resolve_gate_config(
            approval.agent_id, request_id
        )
        return GateSettings.from_config(config or {}, is_enforced=False)

    async def _transition(
        self, approval_id: str, *, expected: str, event: str, request_id: str, **fields
    ) -> None:
        """조건부 UPDATE 전이. 영향 행 0 이면 중복 처리로 보고 중단한다."""
        new_status = ApprovalPolicy.next_status(expected, event)
        applied = await self._repo.compare_and_set_status(
            approval_id, expected=expected, new_status=new_status,
            request_id=request_id, **fields,
        )
        if not applied:
            raise ApprovalConflictError(
                f"{approval_id}: expected={expected} no longer holds"
            )

    async def _schedule(
        self, approval: ApprovalRequest, execute_after: datetime, request_id: str
    ) -> ApprovalRequest:
        await self._transition(
            approval.id, expected="approved", event="schedule",
            request_id=request_id, execute_after=execute_after,
        )
        self._logger.info(
            "approval scheduled", request_id=request_id,
            approval_id=approval.id, execute_after=execute_after.isoformat(),
        )
        approval.status = "scheduled"
        approval.execute_after = execute_after
        return approval

    async def _execute_now(
        self, approval: ApprovalRequest, request_id: str
    ) -> ApprovalRequest:
        result = await self._executor.execute(
            tool_id=approval.tool_id, tool_args=approval.tool_args,
            request_id=request_id,
            # approval-gate-phase2 D-05: 대상 시스템이 재승인 중복을 걸러내도록.
            idempotency_key=approval.idempotency_key,
        )
        now = self._now()
        if result.ok:
            await self._transition(
                approval.id, expected="approved", event="execute",
                request_id=request_id, executed_at=now,
            )
            approval.status = "executed"
            approval.executed_at = now
            await self._resume(approval, result.output, request_id)
        else:
            # FR-25: 자동 재시도하지 않는다 — 비가역 작업의 재시도는 이중
            # 집행 위험. failed 를 벨에 노출해 사람이 재판단한다.
            await self._transition(
                approval.id, expected="approved", event="fail",
                request_id=request_id, error_message=result.error_message or "실패",
            )
            approval.status = "failed"
            approval.error_message = result.error_message
        self._logger.info(
            "approval executed", request_id=request_id,
            approval_id=approval.id, ok=result.ok,
        )
        return approval


    async def _resume(self, approval, outcome: str, request_id: str) -> None:
        """재개 실패가 승인·집행 결과를 무효로 만들지 않도록 예외를 가둔다."""
        if self._resumer is None:
            return
        try:
            await self._resumer.resume_from_snapshot(
                approval, outcome=outcome, request_id=request_id
            )
        except Exception as e:
            self._logger.error(
                "resume after decision failed",
                request_id=request_id, approval_id=approval.id, exception=e,
            )


def _agent_changed(agent, approval: ApprovalRequest) -> bool:
    updated_at = getattr(agent, "updated_at", None)
    return updated_at is not None and updated_at != approval.snapshot.agent_updated_at




def _utcnow() -> datetime:
    from datetime import timezone

    return datetime.now(timezone.utc).replace(tzinfo=None)
