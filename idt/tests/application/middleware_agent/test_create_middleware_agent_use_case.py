"""CreateMiddlewareAgentUseCase 단위 테스트."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
import pytest

from src.application.middleware_agent.create_middleware_agent_use_case import CreateMiddlewareAgentUseCase
from src.application.middleware_agent.schemas import (
    CreateMiddlewareAgentRequest,
    MiddlewareConfigRequest,
)
from src.domain.middleware_agent.schemas import MiddlewareAgentDefinition, MiddlewareType


def _make_saved_agent(agent_id: str = "saved-uuid") -> MiddlewareAgentDefinition:
    now = datetime(2026, 3, 24)
    return MiddlewareAgentDefinition(
        id=agent_id,
        user_id="user-1",
        name="테스트",
        description="desc",
        system_prompt="prompt",
        model_name="gpt-4o",
        tool_ids=["internal_document_search"],
        middleware_configs=[],
        status="active",
        created_at=now,
        updated_at=now,
    )


def _make_request(**kwargs) -> CreateMiddlewareAgentRequest:
    defaults = dict(
        user_id="user-1",
        name="테스트",
        description="desc",
        system_prompt="you are helpful",
        model_name="gpt-4o",
        tool_ids=["internal_document_search"],
        middleware=[],
        request_id="req-1",
    )
    defaults.update(kwargs)
    return CreateMiddlewareAgentRequest(**defaults)


class TestCreateMiddlewareAgentUseCase:

    def _make_use_case(self, saved_agent=None):
        repo = AsyncMock()
        repo.save = AsyncMock(return_value=saved_agent or _make_saved_agent())
        logger = MagicMock()
        return CreateMiddlewareAgentUseCase(repository=repo, logger=logger), repo

    @pytest.mark.asyncio
    async def test_create_agent_success(self):
        use_case, repo = self._make_use_case()
        request = _make_request()
        response = await use_case.execute(request)
        assert response.agent_id == "saved-uuid"
        assert response.name == "테스트"
        assert response.status == "active"
        repo.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_agent_with_middleware(self):
        mw_cfg = MiddlewareConfigRequest(type="pii", config={"pii_type": "email"})
        saved = _make_saved_agent()
        use_case, repo = self._make_use_case(saved_agent=saved)
        request = _make_request(middleware=[mw_cfg])
        response = await use_case.execute(request)
        assert response.middleware_count == 0  # saved agent has 0 middleware_configs
        repo.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_agent_zero_tools_raises(self):
        use_case, _ = self._make_use_case()
        request = _make_request(tool_ids=[])
        with pytest.raises(ValueError):
            await use_case.execute(request)

    @pytest.mark.asyncio
    async def test_create_agent_too_many_tools_raises(self):
        use_case, _ = self._make_use_case()
        request = _make_request(tool_ids=["a", "b", "c", "d", "e", "f"])
        with pytest.raises(ValueError):
            await use_case.execute(request)

    @pytest.mark.asyncio
    async def test_create_agent_prompt_too_long_raises(self):
        use_case, _ = self._make_use_case()
        request = _make_request(system_prompt="x" * 4001)
        with pytest.raises(ValueError):
            await use_case.execute(request)

    @pytest.mark.asyncio
    async def test_create_agent_duplicate_middleware_raises(self):
        use_case, _ = self._make_use_case()
        mw = [
            MiddlewareConfigRequest(type="pii", config={"pii_type": "email"}),
            MiddlewareConfigRequest(type="pii", config={"pii_type": "credit_card"}),
        ]
        request = _make_request(middleware=mw)
        with pytest.raises(ValueError):
            await use_case.execute(request)

    @pytest.mark.asyncio
    async def test_repository_error_propagates(self):
        repo = AsyncMock()
        repo.save = AsyncMock(side_effect=RuntimeError("DB error"))
        logger = MagicMock()
        use_case = CreateMiddlewareAgentUseCase(repository=repo, logger=logger)
        request = _make_request()
        with pytest.raises(RuntimeError, match="DB error"):
            await use_case.execute(request)
        logger.error.assert_called_once()
