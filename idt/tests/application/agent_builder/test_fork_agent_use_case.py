"""ForkAgentUseCase 단위 테스트."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.fork_agent_use_case import ForkAgentUseCase
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition


def _make_agent(
    agent_id: str = "source-1",
    user_id: str = "owner-1",
    visibility: str = "public",
    status: str = "active",
) -> AgentDefinition:
    return AgentDefinition(
        id=agent_id,
        user_id=user_id,
        name="Source Agent",
        description="desc",
        system_prompt="prompt",
        flow_hint="hint",
        workers=[
            WorkerDefinition(
                tool_id="tool-1",
                worker_id="worker-1",
                description="w desc",
                sort_order=0,
            )
        ],
        llm_model_id="model-1",
        status=status,
        visibility=visibility,
        temperature=0.5,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def deps():
    agent_repo = AsyncMock()
    logger = MagicMock()
    uc = ForkAgentUseCase(agent_repo=agent_repo, logger=logger)
    return uc, agent_repo


@pytest.mark.asyncio
async def test_fork_success(deps):
    uc, agent_repo = deps
    agent_repo.find_by_id.return_value = _make_agent()
    agent_repo.save.side_effect = lambda agent, req_id: agent

    result = await uc.execute("source-1", "forker-1", None, [], "req-1")

    assert result.forked_from == "source-1"
    assert result.name == "Source Agent (사본)"
    assert result.visibility == "private"
    assert result.temperature == 0.5
    assert len(result.workers) == 1
    agent_repo.save.assert_called_once()


@pytest.mark.asyncio
async def test_fork_with_custom_name(deps):
    uc, agent_repo = deps
    agent_repo.find_by_id.return_value = _make_agent()
    agent_repo.save.side_effect = lambda agent, req_id: agent

    result = await uc.execute("source-1", "forker-1", "My Agent", [], "req-1")
    assert result.name == "My Agent"


@pytest.mark.asyncio
async def test_fork_own_agent_fails(deps):
    uc, agent_repo = deps
    agent_repo.find_by_id.return_value = _make_agent(user_id="me")

    with pytest.raises(ValueError, match="자신의 에이전트"):
        await uc.execute("source-1", "me", None, [], "req-1")


@pytest.mark.asyncio
async def test_fork_deleted_agent_fails(deps):
    uc, agent_repo = deps
    agent_repo.find_by_id.return_value = _make_agent(status="deleted")

    with pytest.raises(ValueError, match="삭제된 에이전트"):
        await uc.execute("source-1", "forker-1", None, [], "req-1")


@pytest.mark.asyncio
async def test_fork_private_agent_fails(deps):
    uc, agent_repo = deps
    agent_repo.find_by_id.return_value = _make_agent(visibility="private")

    with pytest.raises(PermissionError):
        await uc.execute("source-1", "forker-1", None, [], "req-1")


@pytest.mark.asyncio
async def test_fork_not_found(deps):
    uc, agent_repo = deps
    agent_repo.find_by_id.return_value = None

    with pytest.raises(ValueError, match="에이전트를 찾을 수 없"):
        await uc.execute("source-1", "forker-1", None, [], "req-1")
