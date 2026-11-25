"""자동 실행 바쁨 판정 규칙 (순수).

Design Ref: firewall-agent design §10.3 — 스케줄·알림 수신이 공유하는 일반 규칙.
같은 에이전트에 사람 결정을 기다리는 승인이 있거나 실행이 진행 중이면 새 회차를 돌리지
않는다.
승인 대기 중에 같은 요청이 쌓이는 것을 막는 것이 목적이다 (Plan F3).
"""

from dataclasses import dataclass
from typing import Literal

BusyReason = Literal["approval_pending", "run_in_progress", "check_failed"]

# approval_request 의 비종료 상태 — ApprovalRequest.is_terminal 의 여집합.
OPEN_APPROVAL_STATUSES: tuple[str, ...] = ("pending", "approved", "scheduled")
ACTIVE_JOB_STATUSES: tuple[str, ...] = ("queued", "running")


@dataclass(frozen=True)
class BusyVerdict:
    busy: bool
    reason: BusyReason | None

    @classmethod
    def idle(cls) -> "BusyVerdict":
        return cls(busy=False, reason=None)

    @classmethod
    def check_failed(cls) -> "BusyVerdict":
        """조회 실패는 바쁨으로 본다 (fail-closed) — 중복 요청보다 한 회차 지연이
        안전."""
        return cls(busy=True, reason="check_failed")


def decide_busy(
    *, open_approval: bool, running_run: bool, active_job: bool
) -> BusyVerdict:
    """첫 일치를 사유로 쓴다: 승인 대기 > 실행 중."""
    if open_approval:
        return BusyVerdict(busy=True, reason="approval_pending")
    if running_run or active_job:
        return BusyVerdict(busy=True, reason="run_in_progress")
    return BusyVerdict.idle()
