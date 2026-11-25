"""바쁨 판정 규칙 — firewall-agent design §10.3."""

from src.domain.agent_automation.busy import (
    OPEN_APPROVAL_STATUSES,
    BusyVerdict,
    decide_busy,
)


def test_idle_when_nothing_is_open():
    verdict = decide_busy(open_approval=False, running_run=False, active_job=False)
    assert verdict == BusyVerdict(busy=False, reason=None)


def test_open_approval_wins_over_running_work():
    verdict = decide_busy(open_approval=True, running_run=True, active_job=True)
    assert verdict == BusyVerdict(busy=True, reason="approval_pending")


def test_running_schedule_run_is_run_in_progress():
    verdict = decide_busy(open_approval=False, running_run=True, active_job=False)
    assert verdict == BusyVerdict(busy=True, reason="run_in_progress")


def test_active_background_job_is_run_in_progress():
    verdict = decide_busy(open_approval=False, running_run=False, active_job=True)
    assert verdict == BusyVerdict(busy=True, reason="run_in_progress")


def test_check_failure_is_fail_closed():
    verdict = BusyVerdict.check_failed()
    assert verdict.busy is True and verdict.reason == "check_failed"


def test_open_approval_statuses_are_the_non_terminal_ones():
    assert OPEN_APPROVAL_STATUSES == ("pending", "approved", "scheduled")
