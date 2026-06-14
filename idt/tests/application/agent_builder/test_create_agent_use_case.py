"""CreateAgentUseCase 단위 테스트 — Mock 의존성."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.schemas import (
    CreateAgentRequest, CreateAgentResponse, RagToolConfigRequest, SubAgentConfigRequest,
)
from src.application.agent_builder.create_agent_use_case import CreateAgentUseCase
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition, WorkflowSkeleton
from src.domain.collection.permission_schemas import CollectionPermission, CollectionScope
from src.domain.llm_model.entity import LlmModel


def _make_worker(tool_id: str, sort_order: int = 0) -> WorkerDefinition:
    return WorkerDefinition(
        tool_id=tool_id,
        worker_id=f"{tool_id}_worker",
        description="테스트",
        sort_order=sort_order,
    )


def _make_default_llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-default",
        provider="openai",
        model_name="gpt-4o",
        display_name="GPT-4o",
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=128000,
        is_active=True,
        is_default=True,
        created_at=now,
        updated_at=now,
    )


def _make_perm(scope: CollectionScope, collection_name: str = "docs") -> CollectionPermission:
    return CollectionPermission(
        collection_name=collection_name,
        owner_id=1,
        scope=scope,
    )


def _make_use_case(
    perm_by_name: dict[str, CollectionPermission] | None = None,
    rag_collection: str | None = None,
    requested_visibility: str = "private",
):
    tool_selector = MagicMock()
    prompt_generator = MagicMock()
    repository = MagicMock()
    llm_model_repository = MagicMock()
    perm_repo = MagicMock()
    logger = MagicMock()

    workers = [_make_worker("tavily_search", 0), _make_worker("excel_export", 1)]
    if rag_collection:
        rag_worker = WorkerDefinition(
            tool_id="internal_document_search",
            worker_id="rag_worker",
            description="RAG",
            sort_order=2,
            tool_config={"collection_name": rag_collection},
        )
        workers.append(rag_worker)

    skeleton = WorkflowSkeleton(workers=workers, flow_hint="search 후 export")
    tool_selector.select = AsyncMock(return_value=skeleton)
    prompt_generator.generate = AsyncMock(return_value="자동 생성된 시스템 프롬프트")

    default_model = _make_default_llm_model()
    llm_model_repository.find_by_id = AsyncMock(return_value=default_model)
    llm_model_repository.find_default = AsyncMock(return_value=default_model)

    async def _find_perm(name, req_id):
        if perm_by_name:
            return perm_by_name.get(name)
        return None

    perm_repo.find_by_collection_name = AsyncMock(side_effect=_find_perm)

    now = datetime.now(timezone.utc)
    saved_agent = AgentDefinition(
        id=str(uuid.uuid4()),
        user_id="user-1",
        name="AI 뉴스 수집기",
        description="AI 관련 뉴스 검색하고 엑셀로 저장하는 에이전트 만들어줘",
        system_prompt="자동 생성된 시스템 프롬프트",
        flow_hint="search 후 export",
        workers=skeleton.workers,
        llm_model_id=default_model.id,
        status="active",
        visibility=requested_visibility,
        created_at=now,
        updated_at=now,
    )
    async def _save_passthrough(agent, req_id):
        return agent

    repository.save = AsyncMock(side_effect=_save_passthrough)

    use_case = CreateAgentUseCase(
        tool_selector=tool_selector,
        prompt_generator=prompt_generator,
        repository=repository,
        llm_model_repository=llm_model_repository,
        perm_repo=perm_repo,
        logger=logger,
    )
    return use_case, tool_selector, prompt_generator, repository, perm_repo


class TestCreateAgentUseCase:
    @pytest.mark.asyncio
    async def test_execute_returns_create_agent_response(self):
        use_case, _, _, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="AI 관련 뉴스 검색하고 엑셀로 저장하는 에이전트 만들어줘",
            name="AI 뉴스 수집기",
            user_id="user-1",
        )
        result = await use_case.execute(request, "req-1")
        assert isinstance(result, CreateAgentResponse)
        assert result.name == "AI 뉴스 수집기"
        assert result.system_prompt == "자동 생성된 시스템 프롬프트"

    @pytest.mark.asyncio
    async def test_execute_calls_tool_selector(self):
        use_case, tool_selector, _, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트 요청", name="테스트", user_id="user-1"
        )
        await use_case.execute(request, "req-1")
        tool_selector.select.assert_awaited_once_with("테스트 요청", "req-1")

    @pytest.mark.asyncio
    async def test_execute_calls_prompt_generator(self):
        use_case, _, prompt_generator, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트 요청", name="테스트", user_id="user-1"
        )
        await use_case.execute(request, "req-1")
        prompt_generator.generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_calls_repository_save(self):
        use_case, _, _, repository, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트 요청", name="테스트", user_id="user-1"
        )
        await use_case.execute(request, "req-1")
        repository.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_response_contains_tool_ids(self):
        use_case, _, _, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트 요청", name="테스트", user_id="user-1"
        )
        result = await use_case.execute(request, "req-1")
        assert set(result.tool_ids) == {"tavily_search", "excel_export"}

    @pytest.mark.asyncio
    async def test_execute_raises_on_tool_count_zero(self):
        use_case, tool_selector, _, _, _ = _make_use_case()
        tool_selector.select = AsyncMock(
            return_value=WorkflowSkeleton(workers=[], flow_hint="")
        )
        request = CreateAgentRequest(
            user_request="요청", name="테스트", user_id="user-1"
        )
        with pytest.raises(ValueError, match="최소"):
            await use_case.execute(request, "req-1")


class TestVisibilityClamping:
    @pytest.mark.asyncio
    async def test_public_clamped_to_private_by_personal_collection(self):
        perm = _make_perm(CollectionScope.PERSONAL, "my-docs")
        use_case, _, _, repo, _ = _make_use_case(
            perm_by_name={"my-docs": perm},
            rag_collection="my-docs",
            requested_visibility="public",
        )
        request = CreateAgentRequest(
            user_request="테스트", name="테스트", user_id="user-1",
            visibility="public",
            tool_configs={
                "internal_document_search": RagToolConfigRequest(
                    collection_name="my-docs"
                )
            },
        )
        result = await use_case.execute(request, "req-1")
        saved_agent = repo.save.call_args[0][0]
        assert saved_agent.visibility == "private"
        assert result.visibility_clamped is True
        assert result.max_visibility == "private"

    @pytest.mark.asyncio
    async def test_public_clamped_to_department_by_department_collection(self):
        perm = _make_perm(CollectionScope.DEPARTMENT, "dept-docs")
        use_case, _, _, repo, _ = _make_use_case(
            perm_by_name={"dept-docs": perm},
            rag_collection="dept-docs",
            requested_visibility="public",
        )
        request = CreateAgentRequest(
            user_request="테스트", name="테스트", user_id="user-1",
            visibility="public",
            department_id="dept-1",
            tool_configs={
                "internal_document_search": RagToolConfigRequest(
                    collection_name="dept-docs"
                )
            },
        )
        result = await use_case.execute(request, "req-1")
        saved_agent = repo.save.call_args[0][0]
        assert saved_agent.visibility == "department"
        assert result.visibility_clamped is True

    @pytest.mark.asyncio
    async def test_no_clamp_when_visibility_within_scope(self):
        perm = _make_perm(CollectionScope.PUBLIC, "pub-docs")
        use_case, _, _, repo, _ = _make_use_case(
            perm_by_name={"pub-docs": perm},
            rag_collection="pub-docs",
            requested_visibility="public",
        )
        request = CreateAgentRequest(
            user_request="테스트", name="테스트", user_id="user-1",
            visibility="public",
            tool_configs={
                "internal_document_search": RagToolConfigRequest(
                    collection_name="pub-docs"
                )
            },
        )
        result = await use_case.execute(request, "req-1")
        saved_agent = repo.save.call_args[0][0]
        assert saved_agent.visibility == "public"
        assert result.visibility_clamped is False

    @pytest.mark.asyncio
    async def test_no_rag_tool_no_clamp(self):
        use_case, _, _, repo, _ = _make_use_case(
            requested_visibility="public",
        )
        request = CreateAgentRequest(
            user_request="테스트", name="테스트", user_id="user-1",
            visibility="public",
        )
        result = await use_case.execute(request, "req-1")
        assert result.visibility_clamped is False
        assert result.max_visibility is None

    @pytest.mark.asyncio
    async def test_explicit_tool_configs_clamp_visibility(self):
        """tool_configs로 직접 선택해도 visibility clamping이 동작한다."""
        perm = _make_perm(CollectionScope.PERSONAL, "my-docs")
        use_case, _, _, repo, _ = _make_use_case(
            perm_by_name={"my-docs": perm},
        )
        request = CreateAgentRequest(
            user_request="테스트",
            name="테스트 에이전트",
            user_id="user-1",
            visibility="public",
            tool_configs={
                "internal:internal_document_search": RagToolConfigRequest(
                    collection_name="my-docs"
                )
            },
        )
        result = await use_case.execute(request, "req-1")
        assert result.visibility == "private"
        assert result.visibility_clamped is True

    @pytest.mark.asyncio
    async def test_unknown_collection_treated_as_personal(self):
        use_case, _, _, repo, _ = _make_use_case(
            perm_by_name={},
            rag_collection="legacy-docs",
            requested_visibility="public",
        )
        request = CreateAgentRequest(
            user_request="테스트", name="테스트", user_id="user-1",
            visibility="public",
            tool_configs={
                "internal_document_search": RagToolConfigRequest(
                    collection_name="legacy-docs"
                )
            },
        )
        result = await use_case.execute(request, "req-1")
        saved_agent = repo.save.call_args[0][0]
        assert saved_agent.visibility == "private"
        assert result.visibility_clamped is True


class TestExplicitToolSelection:
    """tool_configs 명시적 도구 선택 테스트."""

    @pytest.mark.asyncio
    async def test_tool_configs_skips_llm_selector(self):
        """tool_configs 존재 시 ToolSelector.select()를 호출하지 않는다."""
        use_case, tool_selector, _, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트",
            name="테스트 에이전트",
            user_id="user-1",
            tool_configs={
                "internal:internal_document_search": RagToolConfigRequest(
                    collection_name="my-docs"
                )
            },
        )
        await use_case.execute(request, "req-1")
        tool_selector.select.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tool_configs_normalizes_prefix(self):
        """'internal:internal_document_search' → 'internal_document_search'."""
        use_case, _, _, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트",
            name="테스트 에이전트",
            user_id="user-1",
            tool_configs={
                "internal:internal_document_search": RagToolConfigRequest(
                    collection_name="my-docs"
                )
            },
        )
        result = await use_case.execute(request, "req-1")
        assert "internal_document_search" in result.tool_ids

    @pytest.mark.asyncio
    async def test_unknown_tool_id_raises_value_error(self):
        """TOOL_REGISTRY에 없는 tool_id → ValueError."""
        use_case, _, _, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트",
            name="테스트 에이전트",
            user_id="user-1",
            tool_configs={
                "internal:nonexistent_tool": RagToolConfigRequest()
            },
        )
        with pytest.raises(ValueError, match="Unknown tool_id"):
            await use_case.execute(request, "req-1")

    @pytest.mark.asyncio
    async def test_no_tool_configs_uses_llm_selector(self):
        """tool_configs 없을 때 ToolSelector.select() 호출."""
        use_case, tool_selector, _, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트 요청",
            name="테스트",
            user_id="user-1",
        )
        await use_case.execute(request, "req-1")
        tool_selector.select.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_tool_config_applied_to_worker(self):
        """tool_configs의 설정이 WorkerDefinition.tool_config에 적용된다."""
        use_case, _, _, repo, _ = _make_use_case()
        config = RagToolConfigRequest(
            collection_name="my-docs",
            top_k=10,
            search_mode="vector_only",
        )
        request = CreateAgentRequest(
            user_request="테스트",
            name="테스트 에이전트",
            user_id="user-1",
            tool_configs={"internal:internal_document_search": config},
        )
        await use_case.execute(request, "req-1")
        saved_agent = repo.save.call_args[0][0]
        worker = next(
            w for w in saved_agent.workers
            if w.tool_id == "internal_document_search"
        )
        assert worker.tool_config["collection_name"] == "my-docs"
        assert worker.tool_config["top_k"] == 10


class TestExplicitToolIdsSelection:
    """tool_ids 명시적 도구 선택 테스트 (사용자가 화면에서 직접 고른 도구)."""

    @pytest.mark.asyncio
    async def test_tool_ids_skips_llm_selector(self):
        """tool_ids 존재 시 ToolSelector.select()를 호출하지 않는다."""
        use_case, tool_selector, _, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트",
            name="테스트 에이전트",
            user_id="user-1",
            tool_ids=["internal:tavily_search", "internal:excel_export"],
        )
        await use_case.execute(request, "req-1")
        tool_selector.select.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tool_ids_builds_skeleton_with_selected_tools(self):
        """선택한 도구가 그대로 워커로 구성된다."""
        use_case, _, _, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트",
            name="테스트 에이전트",
            user_id="user-1",
            tool_ids=["internal:tavily_search", "internal:python_code_executor"],
        )
        result = await use_case.execute(request, "req-1")
        assert set(result.tool_ids) == {"tavily_search", "python_code_executor"}

    @pytest.mark.asyncio
    async def test_tool_ids_prefix_normalized(self):
        """'internal:tavily_search' → 'tavily_search'."""
        use_case, _, _, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트",
            name="테스트 에이전트",
            user_id="user-1",
            tool_ids=["internal:tavily_search"],
        )
        result = await use_case.execute(request, "req-1")
        assert result.tool_ids == ["tavily_search"]

    @pytest.mark.asyncio
    async def test_tool_ids_with_rag_config_merges_config(self):
        """tool_ids + 매칭되는 tool_configs 시 해당 워커에 설정 주입, 나머지는 None."""
        use_case, _, _, repo, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트",
            name="테스트 에이전트",
            user_id="user-1",
            tool_ids=["internal:internal_document_search", "internal:tavily_search"],
            tool_configs={
                "internal:internal_document_search": RagToolConfigRequest(
                    collection_name="my-docs", top_k=7
                )
            },
        )
        await use_case.execute(request, "req-1")
        saved_agent = repo.save.call_args[0][0]
        rag_worker = next(
            w for w in saved_agent.workers
            if w.tool_id == "internal_document_search"
        )
        assert rag_worker.tool_config["collection_name"] == "my-docs"
        assert rag_worker.tool_config["top_k"] == 7
        tav_worker = next(
            w for w in saved_agent.workers if w.tool_id == "tavily_search"
        )
        assert tav_worker.tool_config is None

    @pytest.mark.asyncio
    async def test_empty_tool_ids_falls_back_to_ai_selection(self):
        """tool_ids 빈 리스트 시 기존 AI 자동 선택 경로 동작."""
        use_case, tool_selector, _, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트 요청",
            name="테스트",
            user_id="user-1",
            tool_ids=[],
        )
        await use_case.execute(request, "req-1")
        tool_selector.select.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_tool_id_in_tool_ids_raises(self):
        """TOOL_REGISTRY에 없는 tool_id(MCP 등) → ValueError."""
        use_case, _, _, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트",
            name="테스트 에이전트",
            user_id="user-1",
            tool_ids=["mcp:server-1:some_tool"],
        )
        with pytest.raises(ValueError, match="Unknown tool_id"):
            await use_case.execute(request, "req-1")


def _make_sub_agent(
    agent_id: str = "sub-agent-1",
    user_id: str = "user-1",
    name: str = "서브 에이전트",
) -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id=agent_id,
        user_id=user_id,
        name=name,
        description="테스트 서브 에이전트",
        system_prompt="서브 프롬프트",
        flow_hint="test",
        workers=[WorkerDefinition("tavily_search", "search_worker", "검색", 0)],
        llm_model_id="model-default",
        status="active",
        created_at=now,
        updated_at=now,
    )


def _make_use_case_with_sub_agent(
    sub_agent: AgentDefinition | None = None,
    is_subscribed: bool = False,
):
    tool_selector = MagicMock()
    prompt_generator = MagicMock()
    repository = MagicMock()
    llm_model_repository = MagicMock()
    perm_repo = MagicMock()
    logger = MagicMock()
    subscription_repo = MagicMock()

    workers = [_make_worker("tavily_search", 0)]
    skeleton = WorkflowSkeleton(workers=workers, flow_hint="search")
    tool_selector.select = AsyncMock(return_value=skeleton)
    prompt_generator.generate = AsyncMock(return_value="시스템 프롬프트")

    default_model = _make_default_llm_model()
    llm_model_repository.find_by_id = AsyncMock(return_value=default_model)
    llm_model_repository.find_default = AsyncMock(return_value=default_model)
    perm_repo.find_by_collection_name = AsyncMock(return_value=None)

    repository.find_by_id = AsyncMock(return_value=sub_agent)

    async def _save_passthrough(agent, req_id):
        return agent
    repository.save = AsyncMock(side_effect=_save_passthrough)

    if is_subscribed:
        subscription_repo.find_by_user_and_agent = AsyncMock(
            return_value=MagicMock()
        )
    else:
        subscription_repo.find_by_user_and_agent = AsyncMock(return_value=None)

    use_case = CreateAgentUseCase(
        tool_selector=tool_selector,
        prompt_generator=prompt_generator,
        repository=repository,
        llm_model_repository=llm_model_repository,
        perm_repo=perm_repo,
        logger=logger,
        subscription_repo=subscription_repo,
    )
    return use_case, repository, subscription_repo


class TestSubAgentComposition:
    """서브 에이전트 조합 기능 테스트."""

    @pytest.mark.asyncio
    async def test_sub_agent_worker_created_for_own_agent(self):
        """본인 소유 에이전트를 서브 에이전트로 추가."""
        sub = _make_sub_agent("sub-1", user_id="user-1", name="검색봇")
        use_case, repo, _ = _make_use_case_with_sub_agent(sub_agent=sub)
        request = CreateAgentRequest(
            user_request="테스트",
            name="복합 에이전트",
            user_id="user-1",
            sub_agent_configs=[
                SubAgentConfigRequest(ref_agent_id="sub-1", description="검색 담당")
            ],
        )
        result = await use_case.execute(request, "req-1")
        assert result.has_sub_agents is True
        sub_workers = [w for w in result.workers if w.worker_type == "sub_agent"]
        assert len(sub_workers) == 1
        assert sub_workers[0].ref_agent_id == "sub-1"

    @pytest.mark.asyncio
    async def test_sub_agent_not_found_raises(self):
        """존재하지 않는 에이전트 참조 시 에러."""
        use_case, _, _ = _make_use_case_with_sub_agent(sub_agent=None)
        request = CreateAgentRequest(
            user_request="테스트",
            name="복합 에이전트",
            user_id="user-1",
            sub_agent_configs=[
                SubAgentConfigRequest(ref_agent_id="missing-id")
            ],
        )
        with pytest.raises(ValueError, match="서브 에이전트를 찾을 수 없습니다"):
            await use_case.execute(request, "req-1")

    @pytest.mark.asyncio
    async def test_sub_agent_deleted_raises(self):
        """삭제된 에이전트 참조 시 에러."""
        sub = _make_sub_agent("sub-1", user_id="user-1")
        sub.status = "deleted"
        use_case, _, _ = _make_use_case_with_sub_agent(sub_agent=sub)
        request = CreateAgentRequest(
            user_request="테스트",
            name="복합 에이전트",
            user_id="user-1",
            sub_agent_configs=[
                SubAgentConfigRequest(ref_agent_id="sub-1")
            ],
        )
        with pytest.raises(ValueError, match="서브 에이전트를 찾을 수 없습니다"):
            await use_case.execute(request, "req-1")

    @pytest.mark.asyncio
    async def test_sub_agent_access_denied_for_other_user_without_subscription(self):
        """타인 소유 에이전트에 구독 없이 접근 시 PermissionError."""
        sub = _make_sub_agent("sub-1", user_id="other-user")
        use_case, _, _ = _make_use_case_with_sub_agent(
            sub_agent=sub, is_subscribed=False
        )
        request = CreateAgentRequest(
            user_request="테스트",
            name="복합 에이전트",
            user_id="user-1",
            sub_agent_configs=[
                SubAgentConfigRequest(ref_agent_id="sub-1")
            ],
        )
        with pytest.raises(PermissionError, match="사용 권한이 없습니다"):
            await use_case.execute(request, "req-1")

    @pytest.mark.asyncio
    async def test_sub_agent_access_allowed_with_subscription(self):
        """타인 에이전트도 구독 시 사용 가능."""
        sub = _make_sub_agent("sub-1", user_id="other-user", name="공유봇")
        use_case, _, _ = _make_use_case_with_sub_agent(
            sub_agent=sub, is_subscribed=True
        )
        request = CreateAgentRequest(
            user_request="테스트",
            name="복합 에이전트",
            user_id="user-1",
            sub_agent_configs=[
                SubAgentConfigRequest(ref_agent_id="sub-1")
            ],
        )
        result = await use_case.execute(request, "req-1")
        assert result.has_sub_agents is True

    @pytest.mark.asyncio
    async def test_mixed_tool_and_sub_agent_workers(self):
        """도구 + 서브 에이전트 혼합 모드."""
        sub = _make_sub_agent("sub-1", user_id="user-1", name="분석봇")
        use_case, repo, _ = _make_use_case_with_sub_agent(sub_agent=sub)
        request = CreateAgentRequest(
            user_request="테스트",
            name="복합 에이전트",
            user_id="user-1",
            sub_agent_configs=[
                SubAgentConfigRequest(ref_agent_id="sub-1", description="분석 담당")
            ],
        )
        result = await use_case.execute(request, "req-1")
        tool_workers = [w for w in result.workers if w.worker_type == "tool"]
        sub_workers = [w for w in result.workers if w.worker_type == "sub_agent"]
        assert len(tool_workers) == 1
        assert len(sub_workers) == 1
        assert tool_workers[0].tool_id == "tavily_search"

    @pytest.mark.asyncio
    async def test_no_sub_agent_configs_backward_compatible(self):
        """sub_agent_configs 없을 때 기존 동작 유지."""
        use_case, _, _ = _make_use_case_with_sub_agent(sub_agent=None)
        request = CreateAgentRequest(
            user_request="테스트",
            name="일반 에이전트",
            user_id="user-1",
        )
        result = await use_case.execute(request, "req-1")
        assert result.has_sub_agents is False
        assert all(w.worker_type == "tool" for w in result.workers)
