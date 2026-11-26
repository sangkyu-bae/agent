"""운영자 명령 — 설정 · 스위치 · 역할 매핑 · 지금 실행 (design §5.1~5.3)."""

from __future__ import annotations

import dataclasses
from unittest.mock import MagicMock

import pytest
from src.application.market_analysis.commands import (
    InvalidSettingError,
    RoleAgentInvalidError,
    RoundBusyError,
    RunNowUseCase,
    SetEnabledUseCase,
    SetRoleAgentsUseCase,
    UpdateSettingsUseCase,
)
from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.domain.market_analysis.value_objects import AgentRole, RoundKind

from .fakes import FakeRoles, FakeSettings

READY = dataclasses.replace(
    MarketAnalysisSetting.defaults(), kis_server_id="kis-1", run_as_user_id="7"
)


class FakeWriter:
    def __init__(self):
        self.saved = []

    async def save(self, setting, *, updated_by, request_id):
        self.saved.append((setting, updated_by))


class FakeChecker:
    def __init__(self, servers=("kis-1", "dart-1"), users=("7",), agents=("a1", "a2")):
        self.servers, self.users, self.agents = set(servers), set(users), set(agents)

    async def mcp_server_active(self, server_id, request_id):
        return server_id in self.servers

    async def user_active(self, user_id, request_id):
        return user_id in self.users

    async def agent_usable(self, agent_id, request_id):
        return agent_id in self.agents


def _update(checker=None):
    writer = FakeWriter()
    uc = UpdateSettingsUseCase(
        writer=writer, checker=checker or FakeChecker(), logger=MagicMock()
    )
    return uc, writer


async def test_update_saves_valid_setting():
    uc, writer = _update()
    s = dataclasses.replace(READY, enabled=True, dart_server_id="dart-1")
    assert await uc.execute(s, updated_by="3", request_id="r") == s
    assert writer.saved == [(s, "3")]


async def test_update_reports_every_field_and_saves_nothing():
    uc, writer = _update()
    s = dataclasses.replace(
        READY,
        enabled=True,
        max_per_round=0,
        kis_server_id="gone",
        perplexity_server_id="nope",
        run_as_user_id="99",
    )
    with pytest.raises(InvalidSettingError) as e:
        await uc.execute(s, updated_by="3", request_id="r")
    assert set(e.value.errors) == {
        "max_per_round",
        "kis_server_id",
        "perplexity_server_id",
        "run_as_user_id",
    }
    assert writer.saved == []


async def test_enabling_requires_kis_and_run_as_user():
    uc, _ = _update()
    s = dataclasses.replace(MarketAnalysisSetting.defaults(), enabled=True)
    with pytest.raises(InvalidSettingError) as e:
        await uc.execute(s, updated_by="3", request_id="r")
    assert set(e.value.errors) == {"kis_server_id", "run_as_user_id"}


async def test_switch_only_changes_enabled():
    writer = FakeWriter()
    uc = SetEnabledUseCase(
        reader=FakeSettings(READY), writer=writer, logger=MagicMock()
    )
    updated = await uc.execute(True, updated_by="3", request_id="r")
    assert updated == dataclasses.replace(READY, enabled=True)

    bare = SetEnabledUseCase(
        reader=FakeSettings(MarketAnalysisSetting.defaults()),
        writer=writer,
        logger=MagicMock(),
    )
    with pytest.raises(InvalidSettingError):
        await bare.execute(True, updated_by="3", request_id="r")
    off = await bare.execute(False, updated_by="3", request_id="r")  # 끄기는 항상 된다
    assert off.enabled is False


async def test_role_agents_are_checked_before_any_write():
    roles = FakeRoles({})
    uc = SetRoleAgentsUseCase(roles=roles, checker=FakeChecker(), logger=MagicMock())
    with pytest.raises(RoleAgentInvalidError) as e:
        await uc.execute(
            {AgentRole.BUY_JUDGE: "a1", AgentRole.SELL_JUDGE: "deleted"},
            updated_by="3",
            request_id="r",
        )
    assert e.value.roles == ["sell_judge"] and roles.sets == []
    result = await uc.execute(
        {AgentRole.BUY_JUDGE: "a1"}, updated_by="3", request_id="r"
    )
    assert result == {AgentRole.BUY_JUDGE: "a1"}


async def test_run_now_busy():
    class Sched:
        def __init__(self, rid):
            self.rid = rid

        async def run_now(self, kind, request_id):
            return self.rid

    assert (
        await RunNowUseCase(scheduler=Sched(5), logger=MagicMock()).execute(
            RoundKind.CLOSE, requested_by="3", request_id="r"
        )
        == 5
    )
    with pytest.raises(RoundBusyError):
        await RunNowUseCase(scheduler=Sched(None), logger=MagicMock()).execute(
            RoundKind.CLOSE, requested_by="3", request_id="r"
        )
