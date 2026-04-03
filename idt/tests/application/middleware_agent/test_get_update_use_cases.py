"""GetMiddlewareAgentUseCase / UpdateMiddlewareAgentUseCase 단위 테스트."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
import pytest

from src.application.middleware_agent.get_middleware_agent_use_case import GetMiddlewareAgentUseCase
from src.application.middleware_agent.update_middleware_agent_use_case import UpdateMiddlewareAgentUseCase
from src.application.middleware_agent.schemas import UpdateMiddlewareAgentRequest
from src.domain.middleware_agent.schemas import (
    MiddlewareAgentDefinition,
    MiddlewareConfig,
    MiddlewareType,
)


def _make_agent() -> MiddlewareAgentDefinition:
    now = datetime(2026, 3, 24)
    return MiddlewareAgentDefinition(
        id="agent-1",
        user_id="user-1",
        name="원본 이름",
        description="desc",
        system_prompt="original prompt",
        model_name="gpt-4o",
        tool_ids=["internal_document_search"],
        middleware_configs=[
            MiddlewareConfig(MiddlewareType.PII, {"pii_type": "email"}, sort_order=0)
        ],
        status="active",
        created_at=now,
        updated_at=now,
    )


class TestGetMiddlewareAgentUseCase:

    @pytest.mark.asyncio
    async def test_get_existing_agent_returns_response(self):
        repo = AsyncMock()
        repo.find_by_id = AsyncMock(return_value=_make_agent())
        logger = MagicMock()
        use_case = GetMiddlewareAgentUseCase(repository=repo, logger=logger)

        response = await use_case.execute("agent-1", request_id="req-1")
        assert response.agent_id == "agent-1"
        assert response.name == "원본 이름"
        assert len(response.middleware) == 1
        repo.find_by_id.assert_awaited_once_with("agent-1")

    @pytest.mark.asyncio
    async def test_get_nonexistent_agent_raises(self):
        repo = AsyncMock()
        repo.find_by_id = AsyncMock(return_value=None)
        logger = MagicMock()
        use_case = GetMiddlewareAgentUseCase(repository=repo, logger=logger)
        with pytest.raises(ValueError, match="not found"):
            await use_case.execute("no-such-id", request_id="req-1")


class TestUpdateMiddlewareAgentUseCase:

    @pytest.mark.asyncio
    async def test_update_system_prompt(self):
        agent = _make_agent()
        repo = AsyncMock()
        repo.find_by_id = AsyncMock(return_value=agent)
        repo.update = AsyncMock(return_value=agent)
        logger = MagicMock()
        use_case = UpdateMiddlewareAgentUseCase(repository=repo, logger=logger)

        request = UpdateMiddlewareAgentRequest(
            system_prompt="new prompt", name=None, middleware=None, request_id="req-1"
        )
        response = await use_case.execute("agent-1", request)
        assert response.system_prompt == "new prompt"
        repo.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_nonexistent_agent_raises(self):
        repo = AsyncMock()
        repo.find_by_id = AsyncMock(return_value=None)
        logger = MagicMock()
        use_case = UpdateMiddlewareAgentUseCase(repository=repo, logger=logger)
        request = UpdateMiddlewareAgentRequest(request_id="req-1")
        with pytest.raises(ValueError, match="not found"):
            await use_case.execute("no-id", request)

    @pytest.mark.asyncio
    async def test_update_prompt_too_long_raises(self):
        agent = _make_agent()
        repo = AsyncMock()
        repo.find_by_id = AsyncMock(return_value=agent)
        logger = MagicMock()
        use_case = UpdateMiddlewareAgentUseCase(repository=repo, logger=logger)
        request = UpdateMiddlewareAgentRequest(
            system_prompt="x" * 4001, request_id="req-1"
        )
        with pytest.raises(ValueError):
            await use_case.execute("agent-1", request)
