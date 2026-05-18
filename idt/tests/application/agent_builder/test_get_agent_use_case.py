"""GetAgentUseCase 단위 테스트."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.get_agent_use_case import GetAgentUseCase
from src.application.agent_builder.schemas import GetAgentResponse
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition


def _make_agent() -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id=str(uuid.uuid4()),
        user_id="user-1",
        name="AI 뉴스 수집기",
        description="AI 관련 뉴스 검색",
        system_prompt="당신은 AI 뉴스 수집 에이전트입니다.",
        flow_hint="search 후 export",
        workers=[WorkerDefinition("tavily_search", "search_worker", "검색", 0)],
        llm_model_id="model-1",
        status="active",
        created_at=now,
        updated_at=now,
    )


def _make_use_case() -> tuple[GetAgentUseCase, MagicMock]:
    repository = MagicMock()
    dept_repository = MagicMock()
    dept_repository.find_by_id = AsyncMock(return_value=None)
    logger = MagicMock()
    agent = _make_agent()
    repository.find_by_id = AsyncMock(return_value=agent)
    use_case = GetAgentUseCase(
        repository=repository,
        dept_repository=dept_repository,
        logger=logger,
    )
    return use_case, repository


class TestGetAgentUseCase:
    @pytest.mark.asyncio
    async def test_execute_returns_get_agent_response(self):
        use_case, _ = _make_use_case()
        result = await use_case.execute("some-id", "req-1")
        assert isinstance(result, GetAgentResponse)

    @pytest.mark.asyncio
    async def test_execute_returns_none_when_not_found(self):
        use_case, repository = _make_use_case()
        repository.find_by_id = AsyncMock(return_value=None)
        result = await use_case.execute("non-existent", "req-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_execute_response_has_correct_agent_id(self):
        use_case, repository = _make_use_case()
        agent = _make_agent()
        repository.find_by_id = AsyncMock(return_value=agent)
        result = await use_case.execute(agent.id, "req-1")
        assert result.agent_id == agent.id

    @pytest.mark.asyncio
    async def test_execute_response_has_workers(self):
        use_case, _ = _make_use_case()
        result = await use_case.execute("some-id", "req-1")
        assert len(result.workers) == 1
        assert result.workers[0].tool_id == "tavily_search"

    @pytest.mark.asyncio
    async def test_execute_raises_on_repository_error(self):
        use_case, repository = _make_use_case()
        repository.find_by_id = AsyncMock(side_effect=RuntimeError("DB error"))
        with pytest.raises(RuntimeError, match="DB error"):
            await use_case.execute("some-id", "req-1")

    @pytest.mark.asyncio
    async def test_execute_includes_sub_agent_worker_fields(self):
        """서브 에이전트 워커의 worker_type, ref_agent_id, ref_agent_name 포함."""
        repository = MagicMock()
        dept_repository = MagicMock()
        dept_repository.find_by_id = AsyncMock(return_value=None)
        logger = MagicMock()

        now = datetime.now(timezone.utc)
        sub_agent = AgentDefinition(
            id="sub-1", user_id="user-1", name="검색봇",
            description="검색", system_prompt="프롬프트", flow_hint="test",
            workers=[], llm_model_id="m1", status="active",
            created_at=now, updated_at=now,
        )
        agent = AgentDefinition(
            id="parent-1", user_id="user-1", name="복합 에이전트",
            description="테스트", system_prompt="프롬프트", flow_hint="test",
            workers=[
                WorkerDefinition("tavily_search", "w0", "검색도구", 0),
                WorkerDefinition(
                    "sub_agent_sub-1", "w1", "서브", 1,
                    worker_type="sub_agent", ref_agent_id="sub-1",
                ),
            ],
            llm_model_id="m1", status="active",
            created_at=now, updated_at=now,
        )

        async def _find_by_id(agent_id, request_id):
            if agent_id == "parent-1":
                return agent
            if agent_id == "sub-1":
                return sub_agent
            return None

        repository.find_by_id = AsyncMock(side_effect=_find_by_id)

        use_case = GetAgentUseCase(
            repository=repository,
            dept_repository=dept_repository,
            logger=logger,
        )
        result = await use_case.execute("parent-1", "req-1")
        sub_worker = next(w for w in result.workers if w.worker_type == "sub_agent")
        assert sub_worker.ref_agent_id == "sub-1"
        assert sub_worker.ref_agent_name == "검색봇"

    @pytest.mark.asyncio
    async def test_execute_populates_department_name(self):
        from src.domain.department.entity import Department
        now = datetime.now(timezone.utc)
        dept = Department(id="dept-1", name="개발팀", description=None, created_at=now, updated_at=now)

        repository = MagicMock()
        dept_repository = MagicMock()
        dept_repository.find_by_id = AsyncMock(return_value=dept)
        logger = MagicMock()

        agent = _make_agent()
        object.__setattr__(agent, "department_id", "dept-1")
        repository.find_by_id = AsyncMock(return_value=agent)

        use_case = GetAgentUseCase(
            repository=repository,
            dept_repository=dept_repository,
            logger=logger,
        )
        result = await use_case.execute(agent.id, "req-1")
        assert result.department_name == "개발팀"
