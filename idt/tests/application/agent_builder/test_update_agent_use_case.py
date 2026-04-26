"""UpdateAgentUseCase 단위 테스트."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.schemas import UpdateAgentRequest, UpdateAgentResponse
from src.application.agent_builder.update_agent_use_case import UpdateAgentUseCase
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.domain.collection.permission_schemas import CollectionPermission, CollectionScope


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
        llm_model_id="model-1",
        status=status,
        created_at=now,
        updated_at=now,
    )


def _make_use_case(
    agent: AgentDefinition | None = None,
    perm_by_name: dict[str, CollectionPermission] | None = None,
):
    repository = MagicMock()
    perm_repo = MagicMock()
    logger = MagicMock()
    _agent = agent or _make_agent()
    repository.find_by_id = AsyncMock(return_value=_agent)
    repository.update = AsyncMock(return_value=_agent)

    async def _find_perm(name, req_id):
        if perm_by_name:
            return perm_by_name.get(name)
        return None

    perm_repo.find_by_collection_name = AsyncMock(side_effect=_find_perm)
    use_case = UpdateAgentUseCase(
        repository=repository, perm_repo=perm_repo, logger=logger
    )
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


class TestUpdateVisibilityScope:
    def _make_rag_agent(
        self, visibility: str = "private", collection_name: str = "docs"
    ) -> AgentDefinition:
        now = datetime.now(timezone.utc)
        return AgentDefinition(
            id=str(uuid.uuid4()),
            user_id="user-1",
            name="RAG 에이전트",
            description="설명",
            system_prompt="프롬프트",
            flow_hint="힌트",
            workers=[
                WorkerDefinition(
                    "internal_document_search", "rag_worker", "RAG", 0,
                    tool_config={"collection_name": collection_name},
                ),
            ],
            llm_model_id="model-1",
            status="active",
            visibility=visibility,
            created_at=now,
            updated_at=now,
        )

    @pytest.mark.asyncio
    async def test_visibility_change_exceeding_scope_raises(self):
        agent = self._make_rag_agent(visibility="private", collection_name="my-docs")
        perm = CollectionPermission(
            collection_name="my-docs", owner_id=1, scope=CollectionScope.PERSONAL,
        )
        use_case, _, _ = _make_use_case(
            agent=agent, perm_by_name={"my-docs": perm}
        )
        request = UpdateAgentRequest(visibility="public")
        with pytest.raises(ValueError, match="최대 허용"):
            await use_case.execute(agent.id, request, "req-1")

    @pytest.mark.asyncio
    async def test_visibility_change_within_scope_succeeds(self):
        agent = self._make_rag_agent(visibility="private", collection_name="pub-docs")
        perm = CollectionPermission(
            collection_name="pub-docs", owner_id=1, scope=CollectionScope.PUBLIC,
        )
        use_case, _, _ = _make_use_case(
            agent=agent, perm_by_name={"pub-docs": perm}
        )
        request = UpdateAgentRequest(visibility="public")
        result = await use_case.execute(agent.id, request, "req-1")
        assert isinstance(result, UpdateAgentResponse)

    @pytest.mark.asyncio
    async def test_no_visibility_change_skips_scope_check(self):
        agent = self._make_rag_agent(visibility="public", collection_name="my-docs")
        perm = CollectionPermission(
            collection_name="my-docs", owner_id=1, scope=CollectionScope.PERSONAL,
        )
        use_case, _, _ = _make_use_case(
            agent=agent, perm_by_name={"my-docs": perm}
        )
        request = UpdateAgentRequest(name="새 이름")
        result = await use_case.execute(agent.id, request, "req-1")
        assert result.name == "새 이름"
