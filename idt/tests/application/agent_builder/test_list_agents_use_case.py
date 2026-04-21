"""ListAgentsUseCase 단위 테스트 — Mock 의존성."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.list_agents_use_case import ListAgentsUseCase
from src.application.agent_builder.schemas import ListAgentsRequest
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition


NOW = datetime.now(timezone.utc)


def _make_agent(
    agent_id: str = "a1",
    user_id: str = "1",
    visibility: str = "private",
    department_id: str | None = None,
) -> AgentDefinition:
    return AgentDefinition(
        id=agent_id, user_id=user_id, name="에이전트",
        description="설명", system_prompt="프롬프트", flow_hint="힌트",
        workers=[WorkerDefinition(tool_id="t", worker_id="w", description="d")],
        llm_model_id="m", status="active",
        visibility=visibility, department_id=department_id,
        temperature=0.7,
        created_at=NOW, updated_at=NOW,
    )


def _make_uc():
    agent_repo = MagicMock()
    dept_repo = MagicMock()
    dept_repo.find_departments_by_user = AsyncMock(return_value=[])
    logger = MagicMock()
    return ListAgentsUseCase(
        agent_repo=agent_repo, dept_repo=dept_repo, logger=logger
    ), agent_repo, dept_repo


class TestListAgentsUseCase:
    @pytest.mark.asyncio
    async def test_scope_mine(self):
        uc, agent_repo, _ = _make_uc()
        agents = [_make_agent("a1", "1")]
        agent_repo.list_accessible = AsyncMock(return_value=(agents, 1))

        req = ListAgentsRequest(scope="mine")
        result = await uc.execute("1", "user", req, "req-1")
        assert result.total == 1
        assert result.agents[0].agent_id == "a1"

    @pytest.mark.asyncio
    async def test_scope_public(self):
        uc, agent_repo, _ = _make_uc()
        agents = [_make_agent("a2", "2", "public")]
        agent_repo.list_accessible = AsyncMock(return_value=(agents, 1))

        req = ListAgentsRequest(scope="public")
        result = await uc.execute("1", "user", req, "req-1")
        assert result.total == 1

    @pytest.mark.asyncio
    async def test_scope_all_merges(self):
        uc, agent_repo, _ = _make_uc()
        agents = [
            _make_agent("a1", "1"),
            _make_agent("a2", "2", "public"),
        ]
        agent_repo.list_accessible = AsyncMock(return_value=(agents, 2))

        req = ListAgentsRequest(scope="all")
        result = await uc.execute("1", "user", req, "req-1")
        assert result.total == 2
        assert len(result.agents) == 2

    @pytest.mark.asyncio
    async def test_can_edit_own_agent(self):
        uc, agent_repo, _ = _make_uc()
        agents = [_make_agent("a1", "1")]
        agent_repo.list_accessible = AsyncMock(return_value=(agents, 1))

        req = ListAgentsRequest(scope="mine")
        result = await uc.execute("1", "user", req, "req-1")
        assert result.agents[0].can_edit is True

    @pytest.mark.asyncio
    async def test_cannot_edit_other_agent(self):
        uc, agent_repo, _ = _make_uc()
        agents = [_make_agent("a2", "2", "public")]
        agent_repo.list_accessible = AsyncMock(return_value=(agents, 1))

        req = ListAgentsRequest(scope="public")
        result = await uc.execute("1", "user", req, "req-1")
        assert result.agents[0].can_edit is False
