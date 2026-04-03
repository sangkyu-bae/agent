"""UpdateAgentUseCase 단위 테스트."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.schemas import UpdateAgentRequest, UpdateAgentResponse
from src.application.agent_builder.update_agent_use_case import UpdateAgentUseCase
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition


def _make_agent(status: str = "active") -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id=str(uuid.uuid4()),
        user_id="user-1",
        name="원래 이름",
        description="설명",
        system_prompt="원래 프롬프트",
        flow_hint="힌트",
        workers=[WorkerDefinition("tavily_search", "search_worker", "검색", 0)],
        model_name="gpt-4o-mini",
        status=status,
        created_at=now,
        updated_at=now,
    )


def _make_use_case(agent: AgentDefinition | None = None):
    repository = MagicMock()
    logger = MagicMock()
    _agent = agent or _make_agent()
    repository.find_by_id = AsyncMock(return_value=_agent)
    repository.update = AsyncMock(return_value=_agent)
    use_case = UpdateAgentUseCase(repository=repository, logger=logger)
    return use_case, repository, _agent


class TestUpdateAgentUseCase:
    @pytest.mark.asyncio
    async def test_execute_updates_system_prompt(self):
        use_case, _, agent = _make_use_case()
        request = UpdateAgentRequest(system_prompt="새 프롬프트")
        result = await use_case.execute(agent.id, request, "req-1")
        assert isinstance(result, UpdateAgentResponse)
        assert result.system_prompt == "새 프롬프트"

    @pytest.mark.asyncio
    async def test_execute_updates_name(self):
        use_case, _, agent = _make_use_case()
        request = UpdateAgentRequest(name="새 이름")
        result = await use_case.execute(agent.id, request, "req-1")
        assert result.name == "새 이름"

    @pytest.mark.asyncio
    async def test_execute_raises_not_found_when_agent_missing(self):
        use_case, repository, _ = _make_use_case()
        repository.find_by_id = AsyncMock(return_value=None)
        request = UpdateAgentRequest(system_prompt="새 프롬프트")
        with pytest.raises(ValueError, match="찾을 수 없"):
            await use_case.execute("non-existent", request, "req-1")

    @pytest.mark.asyncio
    async def test_execute_raises_for_inactive_agent(self):
        inactive_agent = _make_agent(status="inactive")
        use_case, _, _ = _make_use_case(agent=inactive_agent)
        request = UpdateAgentRequest(system_prompt="새 프롬프트")
        with pytest.raises(ValueError, match="비활성화"):
            await use_case.execute(inactive_agent.id, request, "req-1")

    @pytest.mark.asyncio
    async def test_execute_calls_repository_update(self):
        use_case, repository, agent = _make_use_case()
        request = UpdateAgentRequest(system_prompt="새 프롬프트")
        await use_case.execute(agent.id, request, "req-1")
        repository.update.assert_awaited_once()
