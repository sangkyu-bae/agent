"""ExecuteDueApprovalsUseCase 단위 테스트 — 예약 집행 tick.

Design Ref: §2.1 (집행), §4.1 `/internal/approvals/tick`, §8.2 L1 #11·#12.
이중 집행 3차 저지선(claim_due 선점) 위에 2차(조건부 UPDATE)를 겹쳐 쓴다.
"""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.approval.execute_scheduler import ExecuteDueApprovalsUseCase
from src.domain.approval.entity import ApprovalRequest, ResumeSnapshot
from src.domain.approval.interfaces import ExecutionResult

_NOW = datetime(2026, 9, 22, 0, 0, 0)


def _due(approval_id="ap1", tool_id="rate_update") -> ApprovalRequest:
    return ApprovalRequest(
        id=approval_id, run_id="r1", agent_id="ag1", requested_by="sys",
        worker_id="w1", tool_id=tool_id, tool_args={"rate": 3.25},
        draft="기준금리 3.25%", status="scheduled",
        idempotency_key=f"r1:w1:{approval_id}",
        snapshot=ResumeSnapshot(
            schema_version=1, agent_updated_at=_NOW, worker_id="w1",
            state_json='{"messages": []}',
        ),
        expires_at=_NOW + timedelta(hours=9),
        request_id="req1", created_at=_NOW, updated_at=_NOW,
        execute_after=_NOW,
    )


def _uc(*, due=None, cas=True, exec_ok=True, expired=0):
    repo = MagicMock()
    repo.claim_due = AsyncMock(return_value=due if due is not None else [_due()])
    repo.compare_and_set_status = AsyncMock(return_value=cas)
    repo.expire_overdue = AsyncMock(return_value=expired)

    executor = MagicMock()
    executor.execute = AsyncMock(
        return_value=ExecutionResult(
            ok=exec_ok, output="[mock] 집행 완료",
            error_message=None if exec_ok else "SMTP 연결 실패",
        )
    )
    uc = ExecuteDueApprovalsUseCase(
        approval_repo=repo, executor=executor, logger=MagicMock(),
        clock=lambda: _NOW,
    )
    return uc, repo, executor


class TestTick:
    @pytest.mark.asyncio
    async def test_due_건을_집행한다(self):
        uc, _, executor = _uc()
        result = await uc.run("req1")
        assert result.executed_count == 1
        executor.execute.assert_awaited_once()
        assert executor.execute.await_args.kwargs["tool_id"] == "rate_update"

    @pytest.mark.asyncio
    async def test_due가_없으면_아무것도_집행하지_않는다(self):
        uc, _, executor = _uc(due=[])
        result = await uc.run("req1")
        assert result.executed_count == 0
        executor.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_여러_건을_모두_집행한다(self):
        uc, _, executor = _uc(due=[_due("ap1"), _due("ap2"), _due("ap3")])
        result = await uc.run("req1")
        assert result.executed_count == 3
        assert executor.execute.await_count == 3

    @pytest.mark.asyncio
    async def test_선점은_claim_due로_한다(self):
        """다중 tick 워커 이중 집행 방어 3차 저지선."""
        uc, repo, _ = _uc()
        await uc.run("req1")
        repo.claim_due.assert_awaited_once()
        assert repo.claim_due.await_args.args[0] == _NOW


class TestTransition:
    @pytest.mark.asyncio
    async def test_성공하면_executed로_전이(self):
        uc, repo, _ = _uc()
        await uc.run("req1")
        kwargs = repo.compare_and_set_status.await_args.kwargs
        assert kwargs["expected"] == "scheduled"
        assert kwargs["new_status"] == "executed"
        assert kwargs["executed_at"] == _NOW

    @pytest.mark.asyncio
    async def test_실패하면_failed로_전이하고_사유를_남긴다(self):
        uc, repo, _ = _uc(exec_ok=False)
        result = await uc.run("req1")
        assert result.failed_count == 1
        kwargs = repo.compare_and_set_status.await_args.kwargs
        assert kwargs["new_status"] == "failed"
        assert kwargs["error_message"] == "SMTP 연결 실패"

    @pytest.mark.asyncio
    async def test_정산_경합에_지면_성공으로_치지_않는다(self):
        """다른 워커가 이미 정산한 건 — 조건부 UPDATE 가 0 행."""
        uc, _, _ = _uc(cas=False)
        result = await uc.run("req1")
        assert result.executed_count == 0

    @pytest.mark.asyncio
    async def test_집행_중에는_상태를_바꾸지_않는다(self):
        """scheduled → executed 를 미리 해 두면 실패 시 executed → failed 가
        되는데, 전이표상 executed 는 종료 상태라 계약 위반이다.
        중복 집행 방어는 claim_due 의 행 잠금이 담당한다."""
        uc, repo, executor = _uc()
        order = []
        repo.compare_and_set_status = AsyncMock(
            side_effect=lambda *a, **k: (order.append("cas"), True)[1]
        )
        executor.execute = AsyncMock(
            side_effect=lambda **k: (
                order.append("exec"), ExecutionResult(ok=True, output="")
            )[1]
        )
        await uc.run("req1")
        assert order == ["exec", "cas"]

    @pytest.mark.asyncio
    async def test_정산은_항상_scheduled에서_출발한다(self):
        """전이표에 있는 합법 전이만 쓴다 (executed→failed 금지)."""
        uc, repo, _ = _uc(exec_ok=False)
        await uc.run("req1")
        for call in repo.compare_and_set_status.await_args_list:
            assert call.kwargs["expected"] == "scheduled"
            assert call.kwargs["new_status"] in ("executed", "failed")


class TestResilience:
    @pytest.mark.asyncio
    async def test_한_건_실패가_다른_건을_막지_않는다(self):
        uc, _, executor = _uc(due=[_due("ap1"), _due("ap2")])
        executor.execute = AsyncMock(
            side_effect=[
                RuntimeError("집행기 폭발"),
                ExecutionResult(ok=True, output="ok"),
            ]
        )
        result = await uc.run("req1")
        assert result.executed_count == 1
        assert result.failed_count == 1

    @pytest.mark.asyncio
    async def test_예외도_failed로_기록된다(self):
        uc, repo, executor = _uc()
        executor.execute = AsyncMock(side_effect=RuntimeError("폭발"))
        await uc.run("req1")
        kwargs = repo.compare_and_set_status.await_args_list[-1].kwargs
        assert kwargs["new_status"] == "failed"
        assert "폭발" in kwargs["error_message"]


class TestExpiry:
    @pytest.mark.asyncio
    async def test_만료_경과건을_먼저_정리한다(self):
        """만료 건이 due 로 잡혀 집행되면 안 된다."""
        uc, repo, _ = _uc(expired=2)
        result = await uc.run("req1")
        assert result.expired_count == 2
        repo.expire_overdue.assert_awaited_once()


class TestAgentChangedAtExecution:
    """Check G8 — FR-14: 예약 대기 중 에이전트 정의가 바뀌면 **집행은 하고
    재개만 거부**한다. 사람이 승인한 것은 tool_args 에 고정된 부작용 내용
    (이메일 본문·금리값)이지 에이전트 구성이 아니므로 집행을 막지 않는다.
    재개 거부는 resumer(RunAgentUseCase._can_resume)가 판정한다."""

    @pytest.mark.asyncio
    async def test_집행은_진행하고_재개_판정은_resumer에_위임한다(self):
        uc, repo, executor = _uc()
        resumer = MagicMock()
        resumer.resume_from_snapshot = AsyncMock(return_value="")  # 재개 거부
        uc._resumer = resumer
        result = await uc.run("req1")
        assert result.executed_count == 1          # 집행은 됐다
        executor.execute.assert_awaited_once()
        resumer.resume_from_snapshot.assert_awaited_once()  # 판정은 위임

    @pytest.mark.asyncio
    async def test_재개_실패가_집행_성공을_되돌리지_않는다(self):
        uc, repo, _ = _uc()
        resumer = MagicMock()
        resumer.resume_from_snapshot = AsyncMock(side_effect=RuntimeError("x"))
        uc._resumer = resumer
        result = await uc.run("req1")
        assert result.executed_count == 1
        kwargs = repo.compare_and_set_status.await_args.kwargs
        assert kwargs["new_status"] == "executed"
