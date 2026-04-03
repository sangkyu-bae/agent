"""MiddlewareAgentRepository 단위 테스트 (Mock AsyncSession 사용)."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.domain.middleware_agent.schemas import (
    MiddlewareAgentDefinition,
    MiddlewareConfig,
    MiddlewareType,
)
from src.infrastructure.middleware_agent.middleware_agent_repository import MiddlewareAgentRepository
from src.infrastructure.middleware_agent.models import (
    MiddlewareAgentModel,
    MiddlewareAgentToolModel,
    MiddlewareConfigModel,
)


def _make_domain_agent() -> MiddlewareAgentDefinition:
    now = datetime(2026, 3, 24)
    return MiddlewareAgentDefinition(
        id="agent-uuid",
        user_id="user-1",
        name="테스트",
        description="desc",
        system_prompt="prompt",
        model_name="gpt-4o",
        tool_ids=["internal_document_search"],
        middleware_configs=[
            MiddlewareConfig(MiddlewareType.PII, {"pii_type": "email"}, sort_order=0)
        ],
        status="active",
        created_at=now,
        updated_at=now,
    )


def _make_orm_model() -> MiddlewareAgentModel:
    now = datetime(2026, 3, 24)
    model = MiddlewareAgentModel(
        id="agent-uuid",
        user_id="user-1",
        name="테스트",
        description="desc",
        system_prompt="prompt",
        model_name="gpt-4o",
        status="active",
        created_at=now,
        updated_at=now,
    )
    model.tools = [MiddlewareAgentToolModel(tool_id="internal_document_search", sort_order=0)]
    model.middleware_configs = [
        MiddlewareConfigModel(
            middleware_type="pii",
            config_json={"pii_type": "email"},
            sort_order=0,
        )
    ]
    return model


class TestMiddlewareAgentRepository:

    @pytest.mark.asyncio
    async def test_save_calls_session_add_and_flush(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        repo = MiddlewareAgentRepository(session)
        agent = _make_domain_agent()
        result = await repo.save(agent)

        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        assert result.id == "agent-uuid"

    @pytest.mark.asyncio
    async def test_find_by_id_returns_domain_object(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=_make_orm_model())
        session.execute = AsyncMock(return_value=mock_result)

        repo = MiddlewareAgentRepository(session)
        result = await repo.find_by_id("agent-uuid")

        assert result is not None
        assert result.id == "agent-uuid"
        assert result.tool_ids == ["internal_document_search"]
        assert len(result.middleware_configs) == 1
        assert result.middleware_configs[0].middleware_type == MiddlewareType.PII

    @pytest.mark.asyncio
    async def test_find_by_id_returns_none_when_not_found(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=mock_result)

        repo = MiddlewareAgentRepository(session)
        result = await repo.find_by_id("no-such-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_calls_flush(self):
        session = AsyncMock()
        session.get = AsyncMock(return_value=_make_orm_model())
        session.flush = AsyncMock()

        repo = MiddlewareAgentRepository(session)
        agent = _make_domain_agent()
        result = await repo.update(agent)

        session.flush.assert_awaited_once()
        assert result.id == "agent-uuid"

    @pytest.mark.asyncio
    async def test_update_not_found_raises(self):
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)

        repo = MiddlewareAgentRepository(session)
        agent = _make_domain_agent()
        with pytest.raises(ValueError, match="not found"):
            await repo.update(agent)

    def test_to_domain_maps_all_fields(self):
        model = _make_orm_model()
        result = MiddlewareAgentRepository._to_domain(model)
        assert result.id == "agent-uuid"
        assert result.tool_ids == ["internal_document_search"]
        assert result.middleware_configs[0].middleware_type == MiddlewareType.PII
        assert result.middleware_configs[0].config == {"pii_type": "email"}
