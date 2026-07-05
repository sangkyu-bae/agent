"""ListAvailableSubAgentsUseCase 단위 테스트 (가시성 기반).

사용 가능 후보 = 본인 소유 + 전체공개 + 부서공개. `list_accessible(scope="all")`을
재사용하므로 use case는 매핑(source_type/필드)만 책임진다.
"""
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
    visibility: str = "private",
    department_id: str | None = None,
    llm_model_id: str = "model-1",
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
        llm_model_id=llm_model_id,
        status="active",
        visibility=visibility,
        department_id=department_id,
        created_at=now,
        updated_at=now,
    )


def _make_use_case(accessible_agents=None, dept_ids=None):
    agent_repo = MagicMock()
    dept_repo = MagicMock()
    logger = MagicMock()

    agents = accessible_agents or []
    agent_repo.list_accessible = AsyncMock(return_value=(agents, len(agents)))

    memberships = [MagicMock(department_id=d) for d in (dept_ids or [])]
    dept_repo.find_departments_by_user = AsyncMock(return_value=memberships)

    use_case = ListAvailableSubAgentsUseCase(
        agent_repo=agent_repo, dept_repo=dept_repo, logger=logger
    )
    return use_case, agent_repo, dept_repo


class TestListAvailableSubAgents:
    @pytest.mark.asyncio
    async def test_owned_agent_source_type(self):
        owned = _make_agent("a1", "user-1", "내 에이전트")
        use_case, _, _ = _make_use_case(accessible_agents=[owned])
        result = await use_case.execute("user-1", "req-1")
        assert isinstance(result, AvailableSubAgentsResponse)
        assert result.agents[0].source_type == "owned"

    @pytest.mark.asyncio
    async def test_public_agent_source_type(self):
        pub = _make_agent("a2", "other", "공개봇", visibility="public")
        use_case, _, _ = _make_use_case(accessible_agents=[pub])
        result = await use_case.execute("user-1", "req-1")
        assert result.agents[0].source_type == "public"

    @pytest.mark.asyncio
    async def test_department_agent_source_type(self):
        dept = _make_agent(
            "a3", "other", "부서봇", visibility="department", department_id="d1"
        )
        use_case, _, _ = _make_use_case(accessible_agents=[dept], dept_ids=["d1"])
        result = await use_case.execute("user-1", "req-1")
        assert result.agents[0].source_type == "department"

    @pytest.mark.asyncio
    async def test_passes_department_ids_to_repo(self):
        use_case, agent_repo, _ = _make_use_case(dept_ids=["d1", "d2"])
        await use_case.execute("1", "req-1")
        _, kwargs = agent_repo.list_accessible.call_args
        assert kwargs["scope"] == "all"
        assert set(kwargs["viewer_department_ids"]) == {"d1", "d2"}

    @pytest.mark.asyncio
    async def test_has_sub_agents_flag(self):
        agent = _make_agent(
            "a1", "user-1", "복합",
            workers=[
                WorkerDefinition("tavily_search", "w0", "검색", 0),
                WorkerDefinition(
                    "sub_agent_xyz", "w1", "서브", 1,
                    worker_type="sub_agent", ref_agent_id="other-agent",
                ),
            ],
        )
        use_case, _, _ = _make_use_case(accessible_agents=[agent])
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
        use_case, _, _ = _make_use_case(accessible_agents=[agent])
        result = await use_case.execute("user-1", "req-1")
        assert set(result.agents[0].tool_ids) == {"tavily_search", "excel_export"}

    @pytest.mark.asyncio
    async def test_model_and_visibility_passthrough(self):
        agent = _make_agent("a1", "user-1", visibility="public", llm_model_id="m9")
        use_case, _, _ = _make_use_case(accessible_agents=[agent])
        result = await use_case.execute("user-1", "req-1")
        assert result.agents[0].llm_model_id == "m9"
        assert result.agents[0].visibility == "public"

    @pytest.mark.asyncio
    async def test_empty_when_no_agents(self):
        use_case, _, _ = _make_use_case()
        result = await use_case.execute("user-1", "req-1")
        assert len(result.agents) == 0
