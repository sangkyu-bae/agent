"""AutoForkService 단위 테스트."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.auto_fork_service import AutoForkService
from src.domain.agent_builder.schemas import AgentDefinition
from src.domain.agent_builder.subscription import Subscription


def _make_agent(agent_id: str = "agent-1", user_id: str = "owner-1") -> AgentDefinition:
    return AgentDefinition(
        id=agent_id,
        user_id=user_id,
        name="Public Agent",
        description="desc",
        system_prompt="prompt",
        flow_hint="hint",
        workers=[],
        llm_model_id="model-1",
        status="active",
        visibility="public",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_subscription(user_id: str, agent_id: str) -> Subscription:
    return Subscription(
        id=f"sub-{user_id}",
        user_id=user_id,
        agent_id=agent_id,
        is_pinned=False,
        subscribed_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def deps():
    agent_repo = AsyncMock()
    sub_repo = AsyncMock()
    logger = MagicMock()
    service = AutoForkService(
        agent_repo=agent_repo,
        subscription_repo=sub_repo,
        logger=logger,
    )
    return service, agent_repo, sub_repo


@pytest.mark.asyncio
async def test_fork_for_subscribers_creates_forks(deps):
    service, agent_repo, sub_repo = deps
    agent = _make_agent()

    sub_repo.find_subscribers_by_agent.return_value = [
        _make_subscription("user-A", "agent-1"),
        _make_subscription("user-B", "agent-1"),
    ]
    agent_repo.list_by_user.return_value = []
    agent_repo.save.side_effect = lambda a, req_id: a
    sub_repo.delete_by_agent.return_value = 2

    count = await service.fork_for_subscribers(agent, "req-1")

    assert count == 2
    assert agent_repo.save.call_count == 2
    sub_repo.delete_by_agent.assert_called_once_with("agent-1", "req-1")


@pytest.mark.asyncio
async def test_skip_already_forked_users(deps):
    service, agent_repo, sub_repo = deps
    agent = _make_agent()

    sub_repo.find_subscribers_by_agent.return_value = [
        _make_subscription("user-A", "agent-1"),
    ]
    already_forked_agent = AgentDefinition(
        id="forked-1",
        user_id="user-A",
        name="Already Forked",
        description="",
        system_prompt="",
        flow_hint="",
        workers=[],
        llm_model_id="model-1",
        status="active",
        visibility="private",
        forked_from="agent-1",
        forked_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    agent_repo.list_by_user.return_value = [already_forked_agent]
    sub_repo.delete_by_agent.return_value = 1

    count = await service.fork_for_subscribers(agent, "req-1")

    assert count == 0
    agent_repo.save.assert_not_called()


@pytest.mark.asyncio
async def test_no_subscribers_returns_zero(deps):
    service, agent_repo, sub_repo = deps
    agent = _make_agent()
    sub_repo.find_subscribers_by_agent.return_value = []

    count = await service.fork_for_subscribers(agent, "req-1")
    assert count == 0
