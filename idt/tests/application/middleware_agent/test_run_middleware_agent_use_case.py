"""RunMiddlewareAgentUseCase 단위 테스트."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.application.middleware_agent.run_middleware_agent_use_case import RunMiddlewareAgentUseCase
from src.application.middleware_agent.schemas import RunMiddlewareAgentRequest
from src.domain.middleware_agent.schemas import (
    MiddlewareAgentDefinition,
    MiddlewareConfig,
    MiddlewareType,
)


def _make_agent(with_middleware=False) -> MiddlewareAgentDefinition:
    now = datetime(2026, 3, 24)
    middleware = []
    if with_middleware:
        middleware = [MiddlewareConfig(MiddlewareType.PII, {"pii_type": "email"}, sort_order=0)]
    return MiddlewareAgentDefinition(
        id="agent-1",
        user_id="user-1",
        name="테스트",
        description="desc",
        system_prompt="prompt",
        model_name="gpt-4o",
        tool_ids=["internal_document_search"],
        middleware_configs=middleware,
        status="active",
        created_at=now,
        updated_at=now,
    )


def _make_use_case(agent=None):
    repo = AsyncMock()
    repo.find_by_id = AsyncMock(return_value=agent or _make_agent())
    tool_factory = AsyncMock()
    tool_factory.create_async = AsyncMock(return_value=MagicMock(name="search_tool"))
    middleware_builder = MagicMock()
    middleware_builder.build = MagicMock(return_value=[])
    logger = MagicMock()
    return RunMiddlewareAgentUseCase(
        repository=repo,
        tool_factory=tool_factory,
        middleware_builder=middleware_builder,
        logger=logger,
    ), repo, tool_factory, middleware_builder


class TestRunMiddlewareAgentUseCase:

    @pytest.mark.asyncio
    async def test_run_agent_success(self):
        use_case, repo, tool_factory, _ = _make_use_case()

        fake_ai_message = MagicMock()
        fake_ai_message.content = "분석 결과입니다"
        fake_ai_message.name = None

        mock_agent = AsyncMock()
        mock_agent.ainvoke = AsyncMock(return_value={"messages": [fake_ai_message]})

        with patch("src.application.middleware_agent.run_middleware_agent_use_case.create_agent", return_value=mock_agent):
            request = RunMiddlewareAgentRequest(query="분석해줘", request_id="req-1")
            response = await use_case.execute("agent-1", request)

        assert response.answer == "분석 결과입니다"
        assert response.middleware_applied == []
        repo.find_by_id.assert_awaited_once_with("agent-1")
        tool_factory.create_async.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_agent_with_middleware_applied(self):
        agent = _make_agent(with_middleware=True)
        use_case, _, _, middleware_builder = _make_use_case(agent=agent)
        middleware_builder.build = MagicMock(return_value=[MagicMock()])

        fake_msg = MagicMock()
        fake_msg.content = "결과"
        fake_msg.name = None

        mock_agent = AsyncMock()
        mock_agent.ainvoke = AsyncMock(return_value={"messages": [fake_msg]})

        with patch("src.application.middleware_agent.run_middleware_agent_use_case.create_agent", return_value=mock_agent):
            request = RunMiddlewareAgentRequest(query="분석", request_id="req-1")
            response = await use_case.execute("agent-1", request)

        assert response.middleware_applied == ["pii"]

    @pytest.mark.asyncio
    async def test_run_agent_not_found_raises(self):
        repo = AsyncMock()
        repo.find_by_id = AsyncMock(return_value=None)
        use_case = RunMiddlewareAgentUseCase(
            repository=repo,
            tool_factory=AsyncMock(),
            middleware_builder=MagicMock(),
            logger=MagicMock(),
        )
        request = RunMiddlewareAgentRequest(query="q", request_id="req-1")
        with pytest.raises(ValueError, match="not found"):
            await use_case.execute("no-id", request)

    @pytest.mark.asyncio
    async def test_run_agent_tools_used_parsed(self):
        use_case, _, _, _ = _make_use_case()

        tool_msg = MagicMock()
        tool_msg.content = ""
        tool_msg.name = "internal_document_search"

        ai_msg = MagicMock()
        ai_msg.content = "분석 완료"
        ai_msg.name = None

        mock_agent = AsyncMock()
        mock_agent.ainvoke = AsyncMock(return_value={"messages": [tool_msg, ai_msg]})

        with patch("src.application.middleware_agent.run_middleware_agent_use_case.create_agent", return_value=mock_agent):
            request = RunMiddlewareAgentRequest(query="분석", request_id="req-1")
            response = await use_case.execute("agent-1", request)

        assert "internal_document_search" in response.tools_used
