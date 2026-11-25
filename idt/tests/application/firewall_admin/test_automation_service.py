"""방화벽 자동 점검 서비스 — firewall-agent design §4.4 (Plan FR-15~17)."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from src.application.firewall_admin.automation_service import (
    FirewallAutomationService,
)
from src.domain.firewall_admin.errors import AutomationNotConfiguredError
from src.domain.firewall_admin.models import (
    AutomationAlert,
    AutomationSchedule,
    AutomationSnapshot,
)

NOW = datetime(2026, 11, 24, 5, 0, 0)


def _snapshot(*, schedules=1, alert=True) -> AutomationSnapshot:
    return AutomationSnapshot(
        agent_id="a1",
        agent_name="방화벽 보안 에이전트",
        schedules=tuple(
            AutomationSchedule(
                id=f"s{i}",
                name="10분 점검",
                enabled=True,
                cron_expr="*/10 * * * *",
                skip_when_busy=True,
                next_run_at=NOW,
                last_run=None,
            )
            for i in range(schedules)
        ),
        alert=AutomationAlert(
            configured=alert,
            enabled=True if alert else None,
            skip_when_busy=True if alert else None,
            last_result=None,
            last_received_at=None,
        ),
    )


class FakePort:
    def __init__(self, snapshot: AutomationSnapshot | None) -> None:
        self.snapshot = snapshot
        self.calls: list[tuple] = []

    async def load(self, agent_id):
        self.calls.append(("load", agent_id))
        return self.snapshot

    async def set_schedules_enabled(self, agent_id, enabled):
        self.calls.append(("schedules", agent_id, enabled))
        return len(self.snapshot.schedules) if self.snapshot else 0

    async def set_alert_enabled(self, agent_id, enabled):
        self.calls.append(("alert", agent_id, enabled))
        return bool(self.snapshot and self.snapshot.alert.configured)


def _svc(agent_id="a1", snapshot=None, *, default_snapshot=True):
    port = FakePort(snapshot if snapshot or not default_snapshot else _snapshot())
    logger = MagicMock()
    return (
        FirewallAutomationService(port, agent_id=agent_id, logger=logger),
        port,
        logger,
    )


class TestState:
    @pytest.mark.asyncio
    async def test_agent_not_set(self):
        svc, port, _ = _svc(agent_id="  ")
        state = await svc.state()
        assert (state.configured, state.reason, state.snapshot) == (
            False,
            "AGENT_NOT_SET",
            None,
        )
        assert port.calls == []

    @pytest.mark.asyncio
    async def test_agent_not_found(self):
        svc, _, _ = _svc(snapshot=None, default_snapshot=False)
        state = await svc.state()
        assert (state.configured, state.reason) == (False, "AGENT_NOT_FOUND")

    @pytest.mark.asyncio
    async def test_configured(self):
        svc, port, _ = _svc()
        state = await svc.state()
        assert state.configured and state.snapshot.agent_name == "방화벽 보안 에이전트"
        assert port.calls == [("load", "a1")]


class TestUpdate:
    @pytest.mark.asyncio
    async def test_turn_schedules_off_and_log_admin(self):
        svc, port, logger = _svc()
        state = await svc.update(
            schedule_enabled=False, alert_enabled=None, admin_user_id="17"
        )
        assert ("schedules", "a1", False) in port.calls
        assert not any(c[0] == "alert" for c in port.calls)
        assert state.configured
        kwargs = logger.info.call_args.kwargs
        assert kwargs["admin_user_id"] == "17" and kwargs["schedule_enabled"] is False

    @pytest.mark.asyncio
    async def test_both_fields(self):
        svc, port, _ = _svc()
        await svc.update(schedule_enabled=True, alert_enabled=False, admin_user_id="17")
        assert ("schedules", "a1", True) in port.calls and (
            "alert",
            "a1",
            False,
        ) in port.calls

    @pytest.mark.asyncio
    async def test_no_schedule_to_toggle_is_not_configured(self):
        svc, _, _ = _svc(snapshot=_snapshot(schedules=0))
        with pytest.raises(AutomationNotConfiguredError):
            await svc.update(
                schedule_enabled=False, alert_enabled=None, admin_user_id="17"
            )

    @pytest.mark.asyncio
    async def test_no_receiver_to_toggle_is_not_configured(self):
        svc, _, _ = _svc(snapshot=_snapshot(alert=False))
        with pytest.raises(AutomationNotConfiguredError):
            await svc.update(
                schedule_enabled=None, alert_enabled=True, admin_user_id="17"
            )

    @pytest.mark.asyncio
    async def test_agent_not_set_cannot_update(self):
        svc, port, _ = _svc(agent_id="")
        with pytest.raises(AutomationNotConfiguredError):
            await svc.update(
                schedule_enabled=False, alert_enabled=None, admin_user_id="17"
            )
        assert port.calls == []

    @pytest.mark.asyncio
    async def test_empty_update_is_rejected(self):
        svc, _, _ = _svc()
        with pytest.raises(AutomationNotConfiguredError):
            await svc.update(
                schedule_enabled=None, alert_enabled=None, admin_user_id="17"
            )
