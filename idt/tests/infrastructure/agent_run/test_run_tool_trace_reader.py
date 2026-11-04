"""SessionScopedRunToolTraceReader — 실시간 경로의 세션 관리와 실패 흡수 (§2.2, §6)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.agent_run.tool_trace_policy import ToolTrace, ToolTraceItem, ToolTraceKind
from src.domain.agent_run.value_objects import RunId
from src.infrastructure.agent_run.run_tool_trace_reader import (
    SessionScopedRunToolTraceReader,
)

RUN_ID = RunId("11111111-1111-1111-1111-111111111111")
TRACE = ToolTrace(items=[ToolTraceItem(seq=1, kind=ToolTraceKind.TOOL, label="도구")])


def _session_factory() -> tuple[MagicMock, MagicMock]:
    session = MagicMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=context), session


@pytest.mark.asyncio
class TestLoadForRun:
    async def test_builds_service_on_one_session_and_returns_run_trace(self) -> None:
        factory, session = _session_factory()
        service = MagicMock()
        service.build_for_runs = AsyncMock(return_value={RUN_ID.value: TRACE})
        builder = MagicMock(return_value=service)
        reader = SessionScopedRunToolTraceReader(factory, builder, MagicMock())

        assert await reader.load_for_run(RUN_ID, "req") is TRACE
        builder.assert_called_once_with(session)
        service.build_for_runs.assert_awaited_once_with([RUN_ID], "req")

    async def test_run_without_tools_is_none(self) -> None:
        factory, _ = _session_factory()
        service = MagicMock()
        service.build_for_runs = AsyncMock(return_value={})
        reader = SessionScopedRunToolTraceReader(factory, lambda _: service, MagicMock())
        assert await reader.load_for_run(RUN_ID, "req") is None

    async def test_session_failure_returns_none_and_logs_exception(self) -> None:
        error = RuntimeError("pool exhausted")
        factory = MagicMock(side_effect=error)
        logger = MagicMock()
        reader = SessionScopedRunToolTraceReader(factory, MagicMock(), logger)

        assert await reader.load_for_run(RUN_ID, "req") is None
        assert logger.warning.call_args.kwargs["exception"] is error
