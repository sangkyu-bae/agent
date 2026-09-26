"""ExecuteDueApprovalsUseCase: 예약 집행 tick.

Design Ref: §2.1 (집행), §4.1 `/internal/approvals/tick`.

금리 변경처럼 "판단은 미리, 반영은 정시" 인 작업을 위해 승인 시각과 집행
시각을 분리했다. 이 UseCase 가 그 정시를 담당한다.

이중 집행 방어 3중:
  1차 uq_approval_request_idempotency  (적재 단계)
  2차 compare_and_set_status           (여기 — 집행 **전**에 전이)
  3차 claim_due FOR UPDATE SKIP LOCKED (여기 — 다중 워커 선점)

전이를 집행보다 **먼저** 하는 이유: 집행 후 전이하면 그 사이 다른 워커가
같은 건을 집행할 수 있다. 전이에 성공한 워커만 집행 권한을 갖는다.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from src.domain.approval.entity import ApprovalRequest
from src.domain.approval.interfaces import ApprovalRepositoryInterface
from src.domain.approval.policies import ApprovalPolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface


@dataclass(frozen=True)
class TickResult:
    """tick 산출물 — 라우터 응답과 관측 로그가 공유한다."""

    claimed_count: int = 0
    executed_count: int = 0
    failed_count: int = 0
    expired_count: int = 0


class ExecuteDueApprovalsUseCase:
    def __init__(
        self,
        approval_repo: ApprovalRepositoryInterface,
        executor,
        logger: LoggerInterface,
        clock: Callable[[], datetime] | None = None,
        batch_limit: int = 50,
        # approval-gate Design §2.1: 집행 후 런 재개 (미주입 시 생략).
        resumer=None,
    ) -> None:
        self._repo = approval_repo
        self._executor = executor
        self._logger = logger
        self._now = clock or _utcnow
        self._batch_limit = batch_limit
        self._resumer = resumer

    async def run(self, request_id: str) -> TickResult:
        now = self._now()
        # 만료 정리를 먼저 — 만료된 건이 due 로 잡혀 집행되면 안 된다.
        expired = await self._repo.expire_overdue(now, request_id)
        claimed = await self._repo.claim_due(
            now, request_id, limit=self._batch_limit
        )

        executed = failed = 0
        for approval in claimed:
            if await self._process(approval, now, request_id):
                executed += 1
            else:
                failed += 1

        result = TickResult(
            claimed_count=len(claimed), executed_count=executed,
            failed_count=failed, expired_count=expired,
        )
        if claimed or expired:
            self._logger.info(
                "approval tick done", request_id=request_id,
                claimed=result.claimed_count, executed=result.executed_count,
                failed=result.failed_count, expired=result.expired_count,
            )
        return result

    async def _process(
        self, approval: ApprovalRequest, now: datetime, request_id: str
    ) -> bool:
        """한 건 집행 후 결과에 따라 전이. 집행 실패면 False.

        집행 **중에는 상태를 바꾸지 않는다**. `scheduled → executed` 를 미리
        해 두고 실패 시 되돌리면 `executed → failed` 가 되는데, 전이표상
        executed 는 종료 상태라 계약 위반이다. 대신 claim_due 의
        FOR UPDATE SKIP LOCKED 가 tick 트랜잭션 동안 행을 잠가 다른 워커의
        중복 집행을 막는다 — 이것이 3차 저지선의 본래 역할이다.

        한 건의 실패가 나머지 배치를 막지 않도록 예외를 여기서 가둔다.
        """
        try:
            result = await self._executor.execute(
                tool_id=approval.tool_id, tool_args=approval.tool_args,
                request_id=request_id,
                # approval-gate-phase2 D-05: 대상 시스템이 재승인 중복을 걸러내도록.
                idempotency_key=approval.idempotency_key,
                # mcp-identity-header §7: 승인자가 아니라 요청자의 신원으로 집행.
                subject_user_id=approval.requested_by,
            )
        except Exception as e:
            self._logger.error(
                "approval execution raised", request_id=request_id,
                approval_id=approval.id, exception=e,
            )
            await self._settle(
                approval, "fail", request_id,
                error_message=f"{type(e).__name__}: {e}",
            )
            return False

        if not result.ok:
            await self._settle(
                approval, "fail", request_id,
                error_message=result.error_message or "집행 실패",
            )
            return False
        settled = await self._settle(
            approval, "execute", request_id, executed_at=now
        )
        if settled:
            await self._resume(approval, result.output, request_id)
        return settled

    async def _settle(
        self, approval: ApprovalRequest, event: str, request_id: str, **fields
    ) -> bool:
        """scheduled → executed | failed. 둘 다 전이표에 있는 합법 전이다.

        영향 행이 0 이면 다른 워커가 이미 정산한 것이다(정상 경합).
        FR-25 에 따라 실패는 자동 재시도하지 않고 벨에 노출한다.
        """
        applied = await self._repo.compare_and_set_status(
            approval.id,
            expected="scheduled",
            new_status=ApprovalPolicy.next_status("scheduled", event),
            request_id=request_id,
            **fields,
        )
        if not applied:
            self._logger.info(
                "approval already settled by another worker",
                request_id=request_id, approval_id=approval.id,
            )
        return applied and event == "execute"


    async def _resume(self, approval, outcome: str, request_id: str) -> None:
        """재개 실패가 집행 성공을 무효로 만들지 않도록 예외를 가둔다."""
        if self._resumer is None:
            return
        try:
            await self._resumer.resume_from_snapshot(
                approval, outcome=outcome, request_id=request_id
            )
        except Exception as e:
            self._logger.error(
                "resume after scheduled execution failed",
                request_id=request_id, approval_id=approval.id, exception=e,
            )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
