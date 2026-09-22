"""승인 UseCase ↔ 집행기 배선 계약.

Design Ref: approval-gate-phase2-mcp-executor §8.2 통합 (I1~I4).

두 가지를 고정한다.
  - 멱등키가 집행기까지 간다 (D-05) — 재승인 시 이중 집행을 대상 시스템이
    걸러낼 수 있어야 한다.
  - 받을 집행기가 없는 도구는 executed 로 기록되지 않는다 (Plan SC-2) —
    Phase 1 의 Mock 폴백이 만들던 가짜 성공을 되살리지 않는다.
"""
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.application.approval.decide_use_case import DecideApprovalUseCase
from src.application.approval.execute_scheduler import ExecuteDueApprovalsUseCase
from src.domain.approval.entity import ApprovalRequest, ResumeSnapshot
from src.domain.approval.interfaces import ExecutionResult
from src.infrastructure.approval.composite_executor import CompositeActionExecutor

_NOW = datetime(2026, 9, 21, 9, 0, 0)
_KEY = "r1:w1:tc1"


def _approval(status: str, tool_id: str = "internal_no_executor") -> ApprovalRequest:
    return ApprovalRequest(
        id="ap1", run_id="r1", agent_id="ag1", requested_by="sys",
        worker_id="w1", tool_id=tool_id, tool_args={"to": "a@b.c"},
        draft="본문", status=status, idempotency_key=_KEY,
        snapshot=ResumeSnapshot(
            schema_version=1, agent_updated_at=_NOW, worker_id="w1",
            state_json='{"messages": []}',
        ),
        expires_at=_NOW + timedelta(hours=24),
        request_id="req1", created_at=_NOW, updated_at=_NOW,
        execute_after=_NOW if status == "scheduled" else None,
    )


def _spy_executor() -> MagicMock:
    executor = MagicMock()
    executor.execute = AsyncMock(return_value=ExecutionResult(ok=True, output="ok"))
    return executor


def _empty_composite() -> CompositeActionExecutor:
    return CompositeActionExecutor(executors=[], logger=MagicMock())


def _decide_uc(executor):
    repo = MagicMock()
    repo.find = AsyncMock(return_value=_approval("pending"))
    repo.compare_and_set_status = AsyncMock(return_value=True)
    agent = MagicMock(user_id="u1", updated_at=_NOW)
    agent_repo = MagicMock()
    agent_repo.find_by_id = AsyncMock(return_value=agent)
    gate = MagicMock()
    gate.resolve_gate_config = AsyncMock(return_value={})
    uc = DecideApprovalUseCase(
        approval_repo=repo, agent_repo=agent_repo, executor=executor,
        gate_config_reader=gate, logger=MagicMock(), clock=lambda: _NOW,
    )
    return uc, repo


def _scheduler_uc(executor):
    repo = MagicMock()
    repo.claim_due = AsyncMock(return_value=[_approval("scheduled")])
    repo.compare_and_set_status = AsyncMock(return_value=True)
    repo.expire_overdue = AsyncMock(return_value=0)
    uc = ExecuteDueApprovalsUseCase(
        approval_repo=repo, executor=executor, logger=MagicMock(),
        clock=lambda: _NOW,
    )
    return uc, repo


def _new_statuses(repo) -> list[str]:
    return [
        call.kwargs["new_status"]
        for call in repo.compare_and_set_status.await_args_list
    ]


class TestIdempotencyKeyReachesExecutor:
    async def test_즉시_집행(self):
        executor = _spy_executor()
        uc, _ = _decide_uc(executor)
        await uc.approve("ap1", user_id="u1", request_id="req1")
        assert executor.execute.await_args.kwargs["idempotency_key"] == _KEY

    async def test_예약_집행(self):
        executor = _spy_executor()
        uc, _ = _scheduler_uc(executor)
        await uc.run("req1")
        assert executor.execute.await_args.kwargs["idempotency_key"] == _KEY


class TestNoExecutorNeverMarksExecuted:
    async def test_즉시_집행은_failed로_끝난다(self):
        uc, repo = _decide_uc(_empty_composite())
        result = await uc.approve("ap1", user_id="u1", request_id="req1")
        statuses = _new_statuses(repo)
        assert "executed" not in statuses
        assert statuses[-1] == "failed"
        assert result.status == "failed"

    async def test_예약_집행은_failed로_끝난다(self):
        uc, repo = _scheduler_uc(_empty_composite())
        result = await uc.run("req1")
        statuses = _new_statuses(repo)
        assert "executed" not in statuses
        assert statuses[-1] == "failed"
        assert result.executed_count == 0

    async def test_실패_사유가_영속된다(self):
        uc, repo = _scheduler_uc(_empty_composite())
        await uc.run("req1")
        message = repo.compare_and_set_status.await_args_list[-1].kwargs[
            "error_message"
        ]
        assert message.startswith("[집행 불가]")


class TestProductionWiring:
    def test_프로덕션_배선에_Mock이_없다(self):
        """Plan SC-8 — supports()=True 인 집행기가 다시 꽂히지 않게 한다."""
        source = Path("src/api/main.py").read_text(encoding="utf-8")
        assert "MockActionExecutor" not in source
        assert "mock_executor" not in source

    def test_src에_Mock_집행기가_없다(self):
        """D-06 — 테스트 더블은 tests/support 에 둔다."""
        assert not Path("src/infrastructure/approval/mock_executor.py").exists()
