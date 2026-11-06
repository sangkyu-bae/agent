"""SessionScopedRunSourcesReader — 실시간 경로의 세션 관리와 실패 흡수."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.agent_run.source_policy import RunSourceItem, SourceKind
from src.domain.agent_run.value_objects import RunId
from src.infrastructure.agent_run.run_sources_reader import (
    SessionScopedRunSourcesReader,
)

RUN_ID = RunId("11111111-1111-1111-1111-111111111111")
ITEM = RunSourceItem(SourceKind.DOCUMENT, "a.pdf", "발췌", "doc-1")


def _session_factory() -> tuple[MagicMock, MagicMock]:
    session = MagicMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=context), session


@pytest.mark.asyncio
class TestLoadForRun:
    async def test_builds_service_on_one_session_and_returns_run_items(self) -> None:
        factory, session = _session_factory()
        service = MagicMock()
        service.build_for_runs = AsyncMock(return_value={RUN_ID.value: [ITEM]})
        builder = MagicMock(return_value=service)
        reader = SessionScopedRunSourcesReader(factory, builder, MagicMock())

        assert await reader.load_for_run(RUN_ID, "req") == [ITEM]
        builder.assert_called_once_with(session)
        service.build_for_runs.assert_awaited_once_with([RUN_ID], "req")

    async def test_run_without_sources_is_empty(self) -> None:
        factory, _ = _session_factory()
        service = MagicMock()
        service.build_for_runs = AsyncMock(return_value={})
        reader = SessionScopedRunSourcesReader(factory, lambda _: service, MagicMock())
        assert await reader.load_for_run(RUN_ID, "req") == []

    async def test_session_failure_returns_empty_and_logs_exception(self) -> None:
        error = RuntimeError("pool exhausted")
        factory = MagicMock(side_effect=error)
        logger = MagicMock()
        reader = SessionScopedRunSourcesReader(factory, MagicMock(), logger)

        assert await reader.load_for_run(RUN_ID, "req") == []
        assert logger.warning.call_args.kwargs["exception"] is error
