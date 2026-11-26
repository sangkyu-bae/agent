"""PlatformAgentCreator — 플랫폼 CreateAgentUseCase 래핑 (design §5.1 bootstrap)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.infrastructure.market_analysis.adapters.agent_creator import (
    PlatformAgentCreator,
)


class FakeCreateUseCase:
    def __init__(self, fail: Exception | None = None):
        self.calls: list[tuple] = []
        self.fail = fail

    async def execute(self, request, request_id, viewer_role="user"):
        self.calls.append((request, viewer_role))
        if self.fail:
            raise self.fail
        return SimpleNamespace(agent_id="agent-9")


def _creator(uc, role="admin"):
    class Session:
        @asynccontextmanager
        async def begin(self):
            yield self

    @asynccontextmanager
    async def sf():
        yield Session()

    return PlatformAgentCreator(
        session_factory=sf,
        create_uc_builder=lambda s: uc,
        viewer_role=role,
        logger=MagicMock(),
    )


async def test_builds_request_with_prompt_tools_and_private_visibility():
    uc = FakeCreateUseCase()
    agent_id, error = await _creator(uc).create(
        name="[시장 분석] 수급",
        system_prompt="지침",
        tool_ids=["mcp:kis-1:get_investor_flow"],
        owner_user_id="7",
        token_limit=40_000,
        request_id="r",
    )
    assert (agent_id, error) == ("agent-9", None)
    request, role = uc.calls[0]
    assert (request.name, request.system_prompt, request.user_id) == (
        "[시장 분석] 수급",
        "지침",
        "7",
    )
    assert request.tool_ids == ["mcp:kis-1:get_investor_flow"]
    assert request.visibility == "private" and request.llm_model_id is None
    assert request.token_limit == 40_000 and role == "admin"
    assert request.user_request  # 필수 필드


async def test_empty_tool_list_is_sent_as_no_tools():
    uc = FakeCreateUseCase()
    await _creator(uc).create(
        name="n",
        system_prompt="p",
        tool_ids=[],
        owner_user_id="7",
        token_limit=60_000,
        request_id="r",
    )
    assert uc.calls[0][0].tool_ids is None


async def test_failure_is_returned_not_raised():
    uc = FakeCreateUseCase(fail=ValueError("unknown tool mcp:kis-1:get_quote"))
    agent_id, error = await _creator(uc).create(
        name="n",
        system_prompt="p",
        tool_ids=["x"],
        owner_user_id="7",
        token_limit=60_000,
        request_id="r",
    )
    assert agent_id is None and "unknown tool" in error
