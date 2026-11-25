"""AgentBusyChecker — firewall-agent design §10.3 (fail-closed)."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.application.agent_automation.busy_checker import AgentBusyChecker
from src.domain.agent_automation.busy import BusyVerdict

NOW = datetime(2026, 11, 24, 5, 0, 0)


class _FakeCM:
    def __init__(self, value=None):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *args):
        return False


def _checker(*, approval=False, run=False, job=False, fail=False, stale=1800):
    reader = MagicMock()
    reader.has_open_approval = AsyncMock(return_value=approval)
    reader.has_running_schedule_run = AsyncMock(return_value=run)
    reader.has_active_job = AsyncMock(return_value=job)
    if fail:
        reader.has_open_approval = AsyncMock(side_effect=RuntimeError("db down"))
    logger = MagicMock()
    checker = AgentBusyChecker(
        session_factory=MagicMock(return_value=_FakeCM(MagicMock())),
        reader_builder=MagicMock(return_value=reader),
        logger=logger,
        stale_seconds=stale,
        now_fn=lambda: NOW,
    )
    return checker, reader, logger


@pytest.mark.asyncio
async def test_idle_agent():
    checker, _, _ = _checker()
    assert await checker.check("a1", "req") == BusyVerdict(busy=False, reason=None)


@pytest.mark.asyncio
async def test_pending_approval_is_busy():
    checker, _, _ = _checker(approval=True, run=True)
    assert await checker.check("a1", "req") == BusyVerdict(
        busy=True, reason="approval_pending"
    )


@pytest.mark.asyncio
async def test_active_job_is_run_in_progress():
    checker, _, _ = _checker(job=True)
    assert (await checker.check("a1", "req")).reason == "run_in_progress"


@pytest.mark.asyncio
async def test_stale_window_is_passed_to_the_reader():
    checker, reader, _ = _checker(stale=600)
    await checker.check("a1", "req")
    since = reader.has_running_schedule_run.call_args[0][1]
    assert since == NOW - timedelta(seconds=600)


@pytest.mark.asyncio
async def test_reader_failure_is_fail_closed_and_logged_with_stack():
    checker, _, logger = _checker(fail=True)
    verdict = await checker.check("a1", "req")
    assert verdict == BusyVerdict(busy=True, reason="check_failed")
    logger.error.assert_called_once()
    assert isinstance(logger.error.call_args.kwargs["exception"], RuntimeError)
