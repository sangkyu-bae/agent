"""ListAvailableSubAgentsUseCase 단위 테스트."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.list_available_sub_agents_use_case import (
    ListAvailableSubAgentsUseCase,
)
from src.application.agent_builder.schemas import AvailableSubAgentsResponse
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition


def _make_agent(
    agent_id: str = "agent-1",
    user_id: str = "user-1",
    name: str = "에이전트",
    workers: list[WorkerDefinition] | None = None,
) -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id=agent_id,
        user_id=user_id,
        name=name,
        description="테스트 에이전트",
        system_prompt="프롬프트",
        flow_hint="test",
        workers=workers or [
            WorkerDefinition("tavily_search", "search_worker", "검색", 0),
        ],
        llm_model_id="model-1",
        status="active",
        created_at=now,
        updated_at=now,
    )


def _make_use_case(owned_agents=None, subscriptions=None, sub_agents=None):
    agent_repo = MagicMock()
    subscription_repo = MagicMock()
    logger = MagicMock()

    agent_repo.list_by_user = AsyncMock(return_value=owned_agents or [])
    subscription_repo.list_by_user = AsyncMock(return_value=subscriptions or [])

    sub_agents_map = {a.id: a for a in (sub_agents or [])}

    async def _find_by_id(agent_id, request_id):
        return sub_agents_map.get(agent_id)

    agent_repo.find_by_id = AsyncMock(side_effect=_find_by_id)

    use_case = ListAvailableSubAgentsUseCase(
        agent_repo=agent_repo,
        subscription_repo=subscription_repo,
        logger=logger,
    )
    return use_case


class TestListAvailableSubAgents:
    @pytest.mark.asyncio
    async def test_returns_owned_agents(self):
        owned = [_make_agent("a1", "user-1", "내 에이전트")]
        use_case = _make_use_case(owned_agents=owned)
        result = await use_case.execute("user-1", "req-1")
        assert isinstance(result, AvailableSubAgentsResponse)
        assert len(result.agents) == 1
        assert result.agents[0].agent_id == "a1"
        assert result.agents[0].source_type == "owned"

    @pytest.mark.asyncio
    async def test_returns_subscribed_agents(self):
        sub_agent = _make_agent("a2", "other-user", "공유 에이전트")
        subscription = MagicMock()
        subscription.agent_id = "a2"
        use_case = _make_use_case(
            subscriptions=[subscription],
            sub_agents=[sub_agent],
        )
        result = await use_case.execute("user-1", "req-1")
        assert len(result.agents) == 1
        assert result.agents[0].source_type == "subscribed"

    @pytest.mark.asyncio
    async def test_merges_owned_and_subscribed(self):
        owned = [_make_agent("a1", "user-1", "내 것")]
        sub_agent = _make_agent("a2", "other-user", "구독 것")
        subscription = MagicMock()
        subscription.agent_id = "a2"
        use_case = _make_use_case(
            owned_agents=owned,
            subscriptions=[subscription],
            sub_agents=[sub_agent],
        )
        result = await use_case.execute("user-1", "req-1")
        assert len(result.agents) == 2

    @pytest.mark.asyncio
    async def test_excludes_deleted_agents(self):
        deleted = _make_agent("a1", "user-1", "삭제됨")
        deleted.status = "deleted"
        use_case = _make_use_case(owned_agents=[deleted])
        result = await use_case.execute("user-1", "req-1")
        assert len(result.agents) == 0

    @pytest.mark.asyncio
    async def test_has_sub_agents_flag(self):
        """이미 서브 에이전트를 포함한 에이전트는 has_sub_agents=True."""
        agent_with_sub = _make_agent(
            "a1", "user-1", "복합 에이전트",
            workers=[
                WorkerDefinition("tavily_search", "w0", "검색", 0),
                WorkerDefinition(
                    "sub_agent_xyz", "w1", "서브", 1,
                    worker_type="sub_agent", ref_agent_id="other-agent",
                ),
            ],
        )
        use_case = _make_use_case(owned_agents=[agent_with_sub])
        result = await use_case.execute("user-1", "req-1")
        assert result.agents[0].has_sub_agents is True

    @pytest.mark.asyncio
    async def test_tool_ids_extracted(self):
        agent = _make_agent(
            "a1", "user-1", "에이전트",
            workers=[
                WorkerDefinition("tavily_search", "w0", "검색", 0),
                WorkerDefinition("excel_export", "w1", "엑셀", 1),
            ],
        )
        use_case = _make_use_case(owned_agents=[agent])
        result = await use_case.execute("user-1", "req-1")
        assert set(result.agents[0].tool_ids) == {"tavily_search", "excel_export"}

    @pytest.mark.asyncio
    async def test_empty_when_no_agents(self):
        use_case = _make_use_case()
        result = await use_case.execute("user-1", "req-1")
        assert len(result.agents) == 0
