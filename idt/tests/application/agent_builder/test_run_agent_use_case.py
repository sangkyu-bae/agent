"""RunAgentUseCase 단위 테스트."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.schemas import RunAgentRequest, RunAgentResponse
from src.application.agent_builder.run_agent_use_case import RunAgentUseCase
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition


def _make_agent() -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id=str(uuid.uuid4()),
        user_id="user-1",
        name="테스트 에이전트",
        description="설명",
        system_prompt="시스템 프롬프트",
        flow_hint="힌트",
        workers=[WorkerDefinition("tavily_search", "search_worker", "검색", 0)],
        model_name="gpt-4o-mini",
        status="active",
        created_at=now,
        updated_at=now,
    )


def _make_use_case():
    repository = MagicMock()
    compiler = MagicMock()
    logger = MagicMock()
    agent = _make_agent()
    repository.find_by_id = AsyncMock(return_value=agent)

    mock_graph = MagicMock()
    last_msg = MagicMock()
    last_msg.content = "AI 뉴스를 수집했습니다."
    last_msg.name = None
    mock_graph.ainvoke = AsyncMock(return_value={
        "messages": [last_msg]
    })
    compiler.compile = MagicMock(return_value=mock_graph)

    use_case = RunAgentUseCase(
        repository=repository,
        compiler=compiler,
        openai_api_key="test-key",
        logger=logger,
    )
    return use_case, repository, compiler, agent


class TestRunAgentUseCase:
    @pytest.mark.asyncio
    async def test_execute_returns_run_agent_response(self):
        use_case, _, _, agent = _make_use_case()
        request = RunAgentRequest(query="AI 뉴스 수집해줘", user_id="user-1")
        result = await use_case.execute(agent.id, request, "req-1")
        assert isinstance(result, RunAgentResponse)
        assert result.agent_id == agent.id
        assert result.query == "AI 뉴스 수집해줘"
        assert result.answer == "AI 뉴스를 수집했습니다."

    @pytest.mark.asyncio
    async def test_execute_raises_not_found_when_agent_missing(self):
        use_case, repository, _, _ = _make_use_case()
        repository.find_by_id = AsyncMock(return_value=None)
        request = RunAgentRequest(query="쿼리", user_id="user-1")
        with pytest.raises(ValueError, match="찾을 수 없"):
            await use_case.execute("non-existent", request, "req-1")

    @pytest.mark.asyncio
    async def test_execute_calls_compiler_compile(self):
        use_case, _, compiler, agent = _make_use_case()
        request = RunAgentRequest(query="쿼리", user_id="user-1")
        await use_case.execute(agent.id, request, "req-1")
        compiler.compile.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_includes_request_id_in_response(self):
        use_case, _, _, agent = _make_use_case()
        request = RunAgentRequest(query="쿼리", user_id="user-1")
        result = await use_case.execute(agent.id, request, "req-xyz")
        assert result.request_id == "req-xyz"
