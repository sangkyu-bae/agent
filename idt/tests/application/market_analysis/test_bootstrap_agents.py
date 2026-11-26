"""기본 에이전트 부트스트랩 — 매핑 없는 역할만 만든다 (design
§5.1 POST /bootstrap-agents, Q6)."""

from __future__ import annotations

import dataclasses
from unittest.mock import MagicMock

import pytest
from src.application.market_analysis.bootstrap_agents import (
    BootstrapAgentsUseCase,
    BootstrapStatus,
)
from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.domain.market_analysis.value_objects import AgentRole

from .fakes import FakeRoles

SETTING = dataclasses.replace(
    MarketAnalysisSetting.defaults(),
    kis_server_id="kis-1",
    dart_server_id="dart-1",
    perplexity_server_id=None,
)


class FakeSettings:
    def __init__(self, setting=SETTING):
        self.setting = setting

    async def get(self, request_id):
        return self.setting


class FakeCreator:
    def __init__(self, fail_names: set[str] | None = None):
        self.created: list[dict] = []
        self.fail_names = fail_names or set()

    async def create(
        self, *, name, system_prompt, tool_ids, owner_user_id, token_limit, request_id
    ):
        self.created.append(
            {
                "name": name,
                "prompt": system_prompt,
                "tools": tool_ids,
                "owner": owner_user_id,
                "token_limit": token_limit,
            }
        )
        if any(f in name for f in self.fail_names):
            return None, "tool catalog missing"
        return f"agent-{len(self.created)}", None


def _uc(roles, creator, setting=SETTING):
    return BootstrapAgentsUseCase(
        roles=roles, creator=creator, settings=FakeSettings(setting), logger=MagicMock()
    )


async def test_creates_all_eleven_when_nothing_mapped():
    roles, creator = FakeRoles({}), FakeCreator()
    items = await _uc(roles, creator).execute(owner_user_id="7", request_id="r")
    assert len(items) == 11 and all(i.status is BootstrapStatus.CREATED for i in items)
    assert set(roles.mapping) == set(AgentRole)
    assert all(c["owner"] == "7" for c in creator.created)
    assert all(c["name"].startswith("[시장 분석] ") for c in creator.created)


async def test_keeps_existing_mappings():
    roles = FakeRoles({AgentRole.BUY_JUDGE: "mine"})
    creator = FakeCreator()
    items = await _uc(roles, creator).execute(owner_user_id="7", request_id="r")
    kept = [i for i in items if i.status is BootstrapStatus.KEPT]
    assert [(i.role, i.agent_id) for i in kept] == [(AgentRole.BUY_JUDGE, "mine")]
    assert roles.mapping[AgentRole.BUY_JUDGE] == "mine"
    assert len(creator.created) == 10


async def test_tool_ids_use_configured_servers_and_skip_missing_ones():
    roles, creator = FakeRoles({}), FakeCreator()
    await _uc(roles, creator).execute(owner_user_id="7", request_id="r")
    by_name = {c["name"]: c for c in creator.created}
    assert by_name["[시장 분석] 기술적 분석"]["tools"] == [
        "mcp:kis-1:get_price_history",
        "mcp:kis-1:compute_indicators",
    ]
    # Perplexity 서버가 설정되지 않아 research 는 빠진다
    assert by_name["[시장 분석] 기업·산업"]["tools"] == ["mcp:dart-1:find_corp"]
    assert by_name["[시장 분석] 뉴스·촉매"]["tools"] == ["tavily_search"]
    assert by_name["[시장 분석] 투자 시나리오"]["tools"] == []
    for c in creator.created:
        assert not any("order" in t for t in c["tools"])


async def test_failures_are_reported_per_role_and_not_mapped():
    roles, creator = FakeRoles({}), FakeCreator(fail_names={"재무"})
    items = await _uc(roles, creator).execute(owner_user_id="7", request_id="r")
    failed = [i for i in items if i.status is BootstrapStatus.FAILED]
    assert [i.role for i in failed] == [AgentRole.SECTION_FINANCIAL]
    assert failed[0].error == "tool catalog missing"
    assert AgentRole.SECTION_FINANCIAL not in roles.mapping


async def test_second_run_is_idempotent():
    roles, creator = FakeRoles({}), FakeCreator()
    uc = _uc(roles, creator)
    await uc.execute(owner_user_id="7", request_id="r")
    items = await uc.execute(owner_user_id="7", request_id="r")
    assert all(i.status is BootstrapStatus.KEPT for i in items)
    assert len(creator.created) == 11


async def test_requires_owner():
    with pytest.raises(ValueError):
        await _uc(FakeRoles({}), FakeCreator()).execute(
            owner_user_id="", request_id="r"
        )
