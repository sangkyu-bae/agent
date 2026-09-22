"""DecideApprovalUseCase 단위 테스트 — 승인/거절.

Design Ref: §2.1 (승인), §4.2 (에러), §8.2 L1 #2~#10.
이중 집행 방어 2차 저지선(조건부 UPDATE)의 호출 계약을 여기서 고정한다.
"""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.approval.decide_use_case import (
    ApprovalAgentChangedError,
    ApprovalConflictError,
    ApprovalExpiredError,
    ApprovalForbiddenError,
    ApprovalInvalidWindowError,
    ApprovalNotFoundError,
    DecideApprovalUseCase,
)
from src.domain.approval.entity import ApprovalRequest, ResumeSnapshot
from src.domain.approval.interfaces import ExecutionResult

_NOW = datetime(2026, 9, 21, 9, 0, 0)


def _request(**over) -> ApprovalRequest:
    base = dict(
        id="ap1", run_id="r1", agent_id="ag1", requested_by="sys",
        worker_id="w1", tool_id="email_send", tool_args={"to": "a@b.c"},
        draft="본문", status="pending", idempotency_key="r1:w1:tc1",
        snapshot=ResumeSnapshot(
            schema_version=1, agent_updated_at=_NOW, worker_id="w1",
            state_json='{"messages": []}',
        ),
        expires_at=_NOW + timedelta(hours=24),
        request_id="req1", created_at=_NOW, updated_at=_NOW,
    )
    base.update(over)
    return ApprovalRequest(**base)


def _uc(*, approval=None, owner="u1", agent_updated_at=_NOW, gate_config=None,
        cas=True, exec_ok=True):
    repo = MagicMock()
    repo.find = AsyncMock(return_value=approval if approval is not None else _request())
    repo.compare_and_set_status = AsyncMock(return_value=cas)

    agent = MagicMock()
    agent.user_id = owner
    agent.updated_at = agent_updated_at
    agent_repo = MagicMock()
    agent_repo.find_by_id = AsyncMock(return_value=agent)

    executor = MagicMock()
    executor.execute = AsyncMock(
        return_value=ExecutionResult(ok=exec_ok, output="[mock] 집행 완료",
                                     error_message=None if exec_ok else "boom")
    )
    gate = MagicMock()
    gate.resolve_gate_config = AsyncMock(return_value=gate_config or {})

    uc = DecideApprovalUseCase(
        approval_repo=repo, agent_repo=agent_repo, executor=executor,
        gate_config_reader=gate, logger=MagicMock(), clock=lambda: _NOW,
    )
    return uc, repo, executor


class TestApproveGuards:
    @pytest.mark.asyncio
    async def test_없는_건은_NotFound(self):
        uc, repo, _ = _uc()
        repo.find = AsyncMock(return_value=None)
        with pytest.raises(ApprovalNotFoundError):
            await uc.approve("ap1", user_id="u1", request_id="req1")

    @pytest.mark.asyncio
    async def test_소유자가_아니면_Forbidden(self):
        uc, _, _ = _uc(owner="다른사람")
        with pytest.raises(ApprovalForbiddenError):
            await uc.approve("ap1", user_id="u1", request_id="req1")

    @pytest.mark.asyncio
    async def test_만료된_건은_Expired(self):
        uc, _, _ = _uc(approval=_request(expires_at=_NOW - timedelta(seconds=1)))
        with pytest.raises(ApprovalExpiredError):
            await uc.approve("ap1", user_id="u1", request_id="req1")

    @pytest.mark.asyncio
    async def test_pending이_아니면_Conflict(self):
        uc, _, _ = _uc(approval=_request(status="executed"))
        with pytest.raises(ApprovalConflictError):
            await uc.approve("ap1", user_id="u1", request_id="req1")

    @pytest.mark.asyncio
    async def test_에이전트_정의가_바뀌었으면_AgentChanged(self):
        """FR-14 — 낡은 스냅샷으로 재개하면 이상 동작한다."""
        uc, _, _ = _uc(agent_updated_at=_NOW + timedelta(days=1))
        with pytest.raises(ApprovalAgentChangedError):
            await uc.approve("ap1", user_id="u1", request_id="req1")

    @pytest.mark.asyncio
    async def test_execute_only면_정의_변경도_통과한다(self):
        """재개는 포기하고 집행만 — 사용자가 명시적으로 선택한 경로."""
        uc, _, executor = _uc(agent_updated_at=_NOW + timedelta(days=1))
        result = await uc.approve(
            "ap1", user_id="u1", request_id="req1", execute_only=True
        )
        assert result.status == "executed"
        executor.execute.assert_awaited_once()


class TestApproveImmediate:
    @pytest.mark.asyncio
    async def test_execute_after가_없으면_즉시_집행(self):
        uc, _, executor = _uc()
        result = await uc.approve("ap1", user_id="u1", request_id="req1")
        assert result.status == "executed"
        executor.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_집행_실패는_failed로_남는다(self):
        """FR-25 — 예외가 아니라 상태로. 자동 재시도 없음."""
        uc, repo, _ = _uc(exec_ok=False)
        result = await uc.approve("ap1", user_id="u1", request_id="req1")
        assert result.status == "failed"
        last = repo.compare_and_set_status.await_args_list[-1]
        assert last.kwargs["new_status"] == "failed"
        assert last.kwargs["error_message"]

    @pytest.mark.asyncio
    async def test_승인_기록이_남는다(self):
        uc, repo, _ = _uc()
        await uc.approve("ap1", user_id="u1", request_id="req1")
        first = repo.compare_and_set_status.await_args_list[0]
        assert first.kwargs["decided_by"] == "u1"
        assert first.kwargs["decided_at"] == _NOW


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_조건부UPDATE가_실패하면_집행하지_않는다(self):
        """중복 클릭 — 두 번째 요청은 영향 행 0 이라 집행이 일어나면 안 된다."""
        uc, _, executor = _uc(cas=False)
        with pytest.raises(ApprovalConflictError):
            await uc.approve("ap1", user_id="u1", request_id="req1")
        executor.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_전이는_expected를_명시해_호출된다(self):
        uc, repo, _ = _uc()
        await uc.approve("ap1", user_id="u1", request_id="req1")
        first = repo.compare_and_set_status.await_args_list[0]
        assert first.kwargs["expected"] == "pending"


class TestApproveScheduled:
    @pytest.mark.asyncio
    async def test_cron이_있으면_scheduled로_예약된다(self):
        """금리 시나리오 — 저녁 승인, 00시 집행."""
        uc, repo, executor = _uc(gate_config={"execute_after": "0 0 * * *"})
        result = await uc.approve("ap1", user_id="u1", request_id="req1")
        assert result.status == "scheduled"
        # Check G13: 이전 기대값 datetime(2026,9,22,0,0) 은 UTC 자정 = KST 09시로,
        # 결함을 그대로 인코딩하고 있었다. KST 18:00(=UTC 09:00) 승인 →
        # 다음 KST 00:00 == 2026-09-21 15:00 UTC 가 올바른 값이다.
        assert result.execute_after == datetime(2026, 9, 21, 15, 0, 0)
        executor.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_집행예정이_만료보다_늦으면_InvalidWindow(self):
        """FR-26 — 승인해도 영원히 집행 안 되는 조합을 차단."""
        uc, _, executor = _uc(
            approval=_request(expires_at=_NOW + timedelta(hours=1)),
            gate_config={"execute_after": "0 0 * * *"},
        )
        with pytest.raises(ApprovalInvalidWindowError):
            await uc.approve("ap1", user_id="u1", request_id="req1")
        executor.execute.assert_not_awaited()


class TestReject:
    @pytest.mark.asyncio
    async def test_사유와_함께_rejected로_전이(self):
        uc, repo, executor = _uc()
        result = await uc.reject(
            "ap1", user_id="u1", reason="한도 초과", request_id="req1"
        )
        assert result.status == "rejected"
        kwargs = repo.compare_and_set_status.await_args.kwargs
        assert kwargs["decision_reason"] == "한도 초과"
        assert kwargs["expected"] == "pending"
        executor.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_빈_사유는_거부한다(self):
        """재개 시 주입되므로 빈 사유는 의미가 없다."""
        uc, _, _ = _uc()
        with pytest.raises(ValueError):
            await uc.reject("ap1", user_id="u1", reason="  ", request_id="req1")

    @pytest.mark.asyncio
    async def test_비소유자_거절도_Forbidden(self):
        uc, _, _ = _uc(owner="다른사람")
        with pytest.raises(ApprovalForbiddenError):
            await uc.reject("ap1", user_id="u1", reason="x", request_id="req1")

    @pytest.mark.asyncio
    async def test_만료건_거절은_Expired(self):
        uc, _, _ = _uc(approval=_request(expires_at=_NOW - timedelta(seconds=1)))
        with pytest.raises(ApprovalExpiredError):
            await uc.reject("ap1", user_id="u1", reason="x", request_id="req1")
