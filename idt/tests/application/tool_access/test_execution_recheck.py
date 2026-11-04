"""승인 집행 직전 권한 재확인 (tool-access-control §0 F4, Design §8.3 R12)."""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

from src.application.tool_access.checker import SessionScopedToolAccessChecker
from src.domain.approval.interfaces import ExecutionResult
from src.domain.tool_access.value_objects import ToolAccessSet
from src.infrastructure.approval.composite_executor import CompositeActionExecutor

TOOL = "mcp:7f3c0000-0000-0000-0000-000000000001:send_mail"


def _inner(ok=True):
    ex = MagicMock()
    ex.supports = MagicMock(return_value=True)
    ex.execute = AsyncMock(return_value=ExecutionResult(ok=ok, output="sent"))
    return ex


def _checker(allowed: bool):
    c = MagicMock()
    c.is_allowed = AsyncMock(return_value=allowed)
    return c


class TestCompositeExecutor:
    async def test_revoked_permission_blocks_before_target_system(self):
        inner = _inner()
        ex = CompositeActionExecutor(executors=[inner], logger=MagicMock(), access_checker=_checker(False))
        res = await ex.execute(tool_id=TOOL, tool_args={}, request_id="r", subject_user_id="7")
        assert res.ok is False
        inner.execute.assert_not_awaited()

    async def test_allowed_executes(self):
        inner = _inner()
        checker = _checker(True)
        ex = CompositeActionExecutor(executors=[inner], logger=MagicMock(), access_checker=checker)
        res = await ex.execute(tool_id=TOOL, tool_args={}, request_id="r", subject_user_id="7")
        assert res.ok is True
        checker.is_allowed.assert_awaited_once_with("7", TOOL, "r")

    async def test_without_checker_behaves_as_before(self):
        inner = _inner()
        ex = CompositeActionExecutor(executors=[inner], logger=MagicMock())
        assert (await ex.execute(tool_id=TOOL, tool_args={}, request_id="r")).ok is True


def _session_factory():
    @asynccontextmanager
    async def factory():
        yield MagicMock()
    return factory


class TestSessionScopedChecker:
    def _checker(self, access=None, error=None):
        resolver = MagicMock()
        resolver.for_user_id = AsyncMock(return_value=access, side_effect=error)
        return SessionScopedToolAccessChecker(
            session_factory=_session_factory(),
            resolver_factory=lambda session: resolver,
            logger=MagicMock(),
        ), resolver

    async def test_allowed(self):
        c, r = self._checker(ToolAccessSet(is_admin=False, allowed=frozenset({TOOL})))
        assert await c.is_allowed("7", TOOL, "r") is True
        r.for_user_id.assert_awaited_once_with("7", "r")

    async def test_denied(self):
        c, _ = self._checker(ToolAccessSet.deny_all())
        assert await c.is_allowed("7", TOOL, "r") is False

    async def test_error_is_denied(self):
        c, _ = self._checker(error=RuntimeError("db"))
        assert await c.is_allowed("7", TOOL, "r") is False
