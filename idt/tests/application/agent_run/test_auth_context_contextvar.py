"""AuthContext ContextVar 단위 테스트.

agent-user-context Design §4.1 검증:
- 미설정 시 None 반환
- set/reset 라이프사이클
- 예외 발생 시에도 token으로 안전 복원
"""
import asyncio

import pytest

from src.application.agent_run.auth_context import (
    get_current_auth_context,
    reset_current_auth_context,
    set_current_auth_context,
)
from src.domain.agent_run.auth_context import AuthContext


def _ctx(user_id: int = 1) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        display_name=f"user-{user_id}",
        role="user",
        primary_department_id=None,
        primary_department_name=None,
        department_ids=(),
        department_names=(),
        permissions=frozenset(),
    )


class TestContextVarLifecycle:
    def test_default_is_none(self):
        assert get_current_auth_context() is None

    def test_set_then_get(self):
        ctx = _ctx(42)
        token = set_current_auth_context(ctx)
        try:
            assert get_current_auth_context() == ctx
        finally:
            reset_current_auth_context(token)

    def test_reset_restores_previous(self):
        ctx = _ctx(1)
        token = set_current_auth_context(ctx)
        assert get_current_auth_context() == ctx
        reset_current_auth_context(token)
        assert get_current_auth_context() is None

    def test_reset_on_exception(self):
        """예외 발생 시에도 finally + reset으로 복원 가능."""
        ctx = _ctx(7)
        token = set_current_auth_context(ctx)
        try:
            raise ValueError("boom")
        except ValueError:
            reset_current_auth_context(token)
        assert get_current_auth_context() is None


class TestContextVarIsolation:
    """asyncio Task별 자동 격리 — 다중 요청 동시 처리에서 혼선 없음."""

    @pytest.mark.asyncio
    async def test_isolated_between_tasks(self):
        async def worker(uid: int, started: asyncio.Event, allow_check: asyncio.Event) -> int | None:
            token = set_current_auth_context(_ctx(uid))
            try:
                started.set()
                await allow_check.wait()
                ctx = get_current_auth_context()
                return ctx.user_id if ctx else None
            finally:
                reset_current_auth_context(token)

        ev1_started = asyncio.Event()
        ev2_started = asyncio.Event()
        allow_check = asyncio.Event()

        t1 = asyncio.create_task(worker(100, ev1_started, allow_check))
        t2 = asyncio.create_task(worker(200, ev2_started, allow_check))

        await ev1_started.wait()
        await ev2_started.wait()
        # 둘 다 set 된 상태에서 동시 check — ContextVar는 task별 독립
        allow_check.set()
        r1, r2 = await asyncio.gather(t1, t2)
        assert r1 == 100
        assert r2 == 200
        # 메인 task에는 영향 없음
        assert get_current_auth_context() is None
