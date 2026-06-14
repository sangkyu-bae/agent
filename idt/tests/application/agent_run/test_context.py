"""RunContext ContextVar 격리 검증 (asyncio Task별 자동 격리)."""
import asyncio
from unittest.mock import MagicMock

import pytest

from src.application.agent_run.context import (
    RunContext,
    get_current_run_context,
    reset_run_context,
    set_current_run_context,
    with_step_id,
    with_tool_call_id,
)
from src.domain.agent_run.value_objects import RunId


def _ctx(run_id: str, user: str = "u") -> RunContext:
    return RunContext(
        run_id=RunId(run_id),
        user_id=user,
        agent_id="a",
        callback=MagicMock(),
    )


class TestContextVarLifecycle:
    def test_default_is_none(self) -> None:
        assert get_current_run_context() is None

    def test_set_and_get(self) -> None:
        ctx = _ctx("11111111-1111-1111-1111-111111111111")
        token = set_current_run_context(ctx)
        try:
            current = get_current_run_context()
            assert current is ctx
        finally:
            reset_run_context(token)
        assert get_current_run_context() is None


class TestAsyncIsolation:
    @pytest.mark.asyncio
    async def test_concurrent_tasks_do_not_share_context(self) -> None:
        """동시 다중 사용자 요청 시 ContextVar이 task별로 분리됨을 보장."""
        observed: dict[str, str | None] = {}

        async def task(name: str, run_id: str) -> None:
            ctx = _ctx(run_id, user=name)
            token = set_current_run_context(ctx)
            try:
                await asyncio.sleep(0)  # 다른 task에게 양보
                current = get_current_run_context()
                observed[name] = current.run_id.value if current else None
            finally:
                reset_run_context(token)

        await asyncio.gather(
            task("alice", "11111111-1111-1111-1111-111111111111"),
            task("bob", "22222222-2222-2222-2222-222222222222"),
        )

        assert observed["alice"] == "11111111-1111-1111-1111-111111111111"
        assert observed["bob"] == "22222222-2222-2222-2222-222222222222"


class TestContextHelpers:
    def test_with_step_id_returns_copy(self) -> None:
        ctx = _ctx("11111111-1111-1111-1111-111111111111")
        new_ctx = with_step_id(ctx, "step-1")
        assert ctx.step_id is None
        assert new_ctx.step_id == "step-1"
        assert new_ctx.run_id == ctx.run_id

    def test_with_tool_call_id_returns_copy(self) -> None:
        ctx = _ctx("11111111-1111-1111-1111-111111111111")
        new_ctx = with_tool_call_id(ctx, "tool-1")
        assert ctx.tool_call_id is None
        assert new_ctx.tool_call_id == "tool-1"
