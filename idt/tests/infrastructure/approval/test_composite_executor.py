"""CompositeActionExecutor 단위 테스트.

Design Ref: approval-gate-phase2-mcp-executor §8.2 (C1~C4).
"""
from unittest.mock import AsyncMock, MagicMock

from src.domain.approval.interfaces import ExecutionResult
from src.infrastructure.approval.composite_executor import CompositeActionExecutor


def _child(*, supports: bool, result: ExecutionResult | None = None, error=None):
    child = MagicMock()
    child.supports = MagicMock(return_value=supports)
    child.execute = AsyncMock(
        return_value=result or ExecutionResult(ok=True, output="done"),
        side_effect=error,
    )
    return child


async def _run(executor, tool_id: str = "mcp:s:t"):
    return await executor.execute(
        tool_id=tool_id, tool_args={"a": 1}, request_id="req1",
        idempotency_key="idem-1",
    )


class TestDelegation:
    async def test_첫_매치_집행기에만_위임한다(self):
        skipped = _child(supports=False)
        first = _child(supports=True)
        second = _child(supports=True)
        executor = CompositeActionExecutor(
            executors=[skipped, first, second], logger=MagicMock()
        )
        result = await _run(executor)
        assert result.ok is True
        skipped.execute.assert_not_awaited()
        second.execute.assert_not_awaited()
        first.execute.assert_awaited_once_with(
            tool_id="mcp:s:t", tool_args={"a": 1}, request_id="req1",
            idempotency_key="idem-1",
        )

    async def test_하위_결과를_그대로_돌려준다(self):
        failed = ExecutionResult(ok=False, output="", error_message="[도구 실패] x")
        executor = CompositeActionExecutor(
            executors=[_child(supports=True, result=failed)], logger=MagicMock()
        )
        assert await _run(executor) is failed


class TestNoExecutor:
    async def test_매치가_없으면_집행_불가로_실패한다(self):
        """Plan SC-2 — executed 로 기록되는 경로가 없어야 한다."""
        executor = CompositeActionExecutor(
            executors=[_child(supports=False)], logger=MagicMock()
        )
        result = await _run(executor, tool_id="internal_unknown")
        assert result.ok is False
        assert result.error_message.startswith("[집행 불가]")
        assert "internal_unknown" in result.error_message

    async def test_집행기_목록이_비어도_실패를_값으로_돌려준다(self):
        executor = CompositeActionExecutor(executors=[], logger=MagicMock())
        result = await _run(executor)
        assert result.ok is False


class TestContractViolation:
    async def test_하위가_예외를_던져도_전파하지_않는다(self):
        """집행 중 예외라 실제 집행 여부를 모른다 — 불명으로 기록한다."""
        error = RuntimeError("GET https://h/mcp?api_key=SECRET failed")
        logger = MagicMock()
        executor = CompositeActionExecutor(
            executors=[_child(supports=True, error=error)], logger=logger
        )
        result = await _run(executor)
        assert result.ok is False
        assert result.error_message.startswith("[집행 여부 불명]")
        assert "SECRET" not in result.error_message
        assert logger.error.call_args.kwargs["exception"] is error


class TestSupports:
    def test_하위_중_하나라도_받으면_True(self):
        executor = CompositeActionExecutor(
            executors=[_child(supports=False), _child(supports=True)],
            logger=MagicMock(),
        )
        assert executor.supports("x") is True

    def test_아무도_못_받으면_False(self):
        executor = CompositeActionExecutor(
            executors=[_child(supports=False)], logger=MagicMock()
        )
        assert executor.supports("x") is False
