"""AgentDefinitionRepository 단위 테스트 — AsyncMock 사용."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.infrastructure.agent_builder.agent_definition_repository import (
    AgentDefinitionRepository,
)


def _make_worker(tool_id: str = "tavily_search", sort_order: int = 0) -> WorkerDefinition:
    return WorkerDefinition(
        tool_id=tool_id,
        worker_id=f"{tool_id}_worker",
        description="테스트 워커",
        sort_order=sort_order,
    )


def _make_agent() -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id=str(uuid.uuid4()),
        user_id="user-1",
        name="테스트 에이전트",
        description="테스트 요청",
        system_prompt="테스트 프롬프트",
        flow_hint="힌트",
        workers=[_make_worker("tavily_search", 0), _make_worker("excel_export", 1)],
        llm_model_id="model-1",
        status="active",
        created_at=now,
        updated_at=now,
    )


def _make_repo() -> tuple[AgentDefinitionRepository, MagicMock]:
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    logger = MagicMock()
    return AgentDefinitionRepository(session=session, logger=logger), session


class TestAgentDefinitionRepositorySave:
    @pytest.mark.asyncio
    async def test_save_adds_model_and_flushes(self):
        repo, session = _make_repo()
        agent = _make_agent()
        result = await repo.save(agent, "req-1")
        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        assert result.id == agent.id

    @pytest.mark.asyncio
    async def test_save_creates_agent_tool_rows(self):
        repo, session = _make_repo()
        agent = _make_agent()
        await repo.save(agent, "req-1")
        added_model = session.add.call_args[0][0]
        assert len(added_model.tools) == 2
        tool_ids = {t.tool_id for t in added_model.tools}
        assert tool_ids == {"tavily_search", "excel_export"}


class TestAgentDefinitionRepositoryFindById:
    @pytest.mark.asyncio
    async def test_find_by_id_returns_none_when_not_found(self):
        repo, session = _make_repo()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        result = await repo.find_by_id("non-existent", "req-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_find_by_id_returns_domain_object(self):
        repo, session = _make_repo()
        now = datetime.now(timezone.utc)

        mock_tool = MagicMock()
        mock_tool.tool_id = "tavily_search"
        mock_tool.worker_id = "search_worker"
        mock_tool.description = "검색"
        mock_tool.sort_order = 0

        mock_model = MagicMock()
        mock_model.id = "agent-1"
        mock_model.user_id = "user-1"
        mock_model.name = "테스트"
        mock_model.description = "설명"
        mock_model.system_prompt = "프롬프트"
        mock_model.flow_hint = "힌트"
        mock_model.llm_model_id = "model-1"
        mock_model.status = "active"
        mock_model.visibility = "private"
        mock_model.department_id = None
        mock_model.temperature = 0.70
        mock_model.created_at = now
        mock_model.updated_at = now
        mock_model.tools = [mock_tool]

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_model
        session.execute.return_value = mock_result

        result = await repo.find_by_id("agent-1", "req-1")
        assert isinstance(result, AgentDefinition)
        assert result.id == "agent-1"
        assert len(result.workers) == 1
        assert result.workers[0].tool_id == "tavily_search"


class TestAgentDefinitionRepositoryUpdate:
    @pytest.mark.asyncio
    async def test_update_modifies_system_prompt_and_name(self):
        repo, session = _make_repo()
        now = datetime.now(timezone.utc)

        mock_model = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_model
        session.execute.return_value = mock_result

        agent = _make_agent()
        agent.system_prompt = "수정된 프롬프트"
        agent.name = "수정된 이름"
        result = await repo.update(agent, "req-1")

        assert mock_model.system_prompt == "수정된 프롬프트"
        assert mock_model.name == "수정된 이름"
        session.flush.assert_awaited_once()
