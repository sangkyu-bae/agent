"""SubscribeUseCase 단위 테스트."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.subscribe_use_case import SubscribeUseCase
from src.domain.agent_builder.schemas import AgentDefinition
from src.domain.agent_builder.subscription import Subscription


def _make_agent(
    agent_id: str = "agent-1",
    user_id: str = "owner-1",
    visibility: str = "public",
) -> AgentDefinition:
    return AgentDefinition(
        id=agent_id,
        user_id=user_id,
        name="Test Agent",
        description="desc",
        system_prompt="prompt",
        flow_hint="hint",
        workers=[],
        llm_model_id="model-1",
        status="active",
        visibility=visibility,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def deps():
    agent_repo = AsyncMock()
    sub_repo = AsyncMock()
    logger = MagicMock()
    uc = SubscribeUseCase(
        agent_repo=agent_repo,
        subscription_repo=sub_repo,
        logger=logger,
    )
    return uc, agent_repo, sub_repo


@pytest.mark.asyncio
async def test_subscribe_success(deps):
    uc, agent_repo, sub_repo = deps
    agent_repo.find_by_id.return_value = _make_agent()
    sub_repo.find_by_user_and_agent.return_value = None
    sub_repo.save.side_effect = lambda sub, req_id: sub

    result = await uc.subscribe("agent-1", "viewer-1", [], "req-1")

    assert result.agent_id == "agent-1"
    assert result.agent_name == "Test Agent"
    assert result.is_pinned is False
    sub_repo.save.assert_called_once()


@pytest.mark.asyncio
async def test_subscribe_own_agent_fails(deps):
    uc, agent_repo, sub_repo = deps
    agent_repo.find_by_id.return_value = _make_agent(user_id="me")

    with pytest.raises(ValueError, match="자신의 에이전트"):
        await uc.subscribe("agent-1", "me", [], "req-1")


@pytest.mark.asyncio
async def test_subscribe_duplicate_fails(deps):
    uc, agent_repo, sub_repo = deps
    agent_repo.find_by_id.return_value = _make_agent()
    sub_repo.find_by_user_and_agent.return_value = Subscription(
        id="sub-1",
        user_id="viewer-1",
        agent_id="agent-1",
        is_pinned=False,
        subscribed_at=datetime.now(timezone.utc),
    )

    with pytest.raises(ValueError, match="이미 구독"):
        await uc.subscribe("agent-1", "viewer-1", [], "req-1")


@pytest.mark.asyncio
async def test_subscribe_private_agent_fails(deps):
    uc, agent_repo, sub_repo = deps
    agent_repo.find_by_id.return_value = _make_agent(visibility="private")

    with pytest.raises(PermissionError):
        await uc.subscribe("agent-1", "viewer-1", [], "req-1")


@pytest.mark.asyncio
async def test_unsubscribe_success(deps):
    uc, agent_repo, sub_repo = deps
    sub_repo.find_by_user_and_agent.return_value = Subscription(
        id="sub-1",
        user_id="viewer-1",
        agent_id="agent-1",
        is_pinned=False,
        subscribed_at=datetime.now(timezone.utc),
    )

    await uc.unsubscribe("agent-1", "viewer-1", "req-1")
    sub_repo.delete.assert_called_once_with("viewer-1", "agent-1", "req-1")


@pytest.mark.asyncio
async def test_unsubscribe_not_found_fails(deps):
    uc, agent_repo, sub_repo = deps
    sub_repo.find_by_user_and_agent.return_value = None

    with pytest.raises(ValueError, match="구독을 찾을 수 없"):
        await uc.unsubscribe("agent-1", "viewer-1", "req-1")


@pytest.mark.asyncio
async def test_update_pin_success(deps):
    uc, agent_repo, sub_repo = deps
    sub_repo.find_by_user_and_agent.return_value = Subscription(
        id="sub-1",
        user_id="viewer-1",
        agent_id="agent-1",
        is_pinned=False,
        subscribed_at=datetime.now(timezone.utc),
    )
    sub_repo.update_pin.return_value = Subscription(
        id="sub-1",
        user_id="viewer-1",
        agent_id="agent-1",
        is_pinned=True,
        subscribed_at=datetime.now(timezone.utc),
    )
    agent_repo.find_by_id.return_value = _make_agent()

    result = await uc.update_pin("agent-1", "viewer-1", True, "req-1")
    assert result.is_pinned is True
