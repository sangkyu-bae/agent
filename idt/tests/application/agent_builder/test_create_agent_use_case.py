"""CreateAgentUseCase 단위 테스트 — Mock 의존성.

agent-instruction-required: 지침(system_prompt) 필수화 + 도구 자동선택 제거.
ToolSelector/PromptGenerator 의존성이 제거되어, 도구는 tool_ids/tool_configs로만
구성되며 미지정 시 워커 0개(순수 대화형)로 생성된다.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.schemas import (
    CreateAgentRequest, CreateAgentResponse, RagToolConfigRequest, SubAgentConfigRequest,
)
from src.application.agent_builder.create_agent_use_case import CreateAgentUseCase
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.domain.collection.permission_schemas import CollectionPermission, CollectionScope
from src.domain.knowledge_base.entities import KnowledgeBase
from src.domain.llm_model.entity import LlmModel

# 테스트 요청 공통 지침 (지침 필수 정책 충족용)
PROMPT = "테스트 지침"


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


def _make_kb(
    kb_id: str,
    scope: CollectionScope,
    collection_name: str = "kb-physical-collection",
    owner_id: int = 1,
    department_id: str | None = None,
) -> KnowledgeBase:
    return KnowledgeBase(
        id=kb_id,
        name=f"kb-{kb_id}",
        owner_id=owner_id,
        scope=scope,
        department_id=department_id,
        collection_name=collection_name,
    )


def _make_use_case(
    perm_by_name: dict[str, CollectionPermission] | None = None,
    kb_by_id: dict[str, KnowledgeBase] | None = None,
    with_kb_repo: bool = True,
    user_dept_ids: list[str] | None = None,
):
    repository = MagicMock()
    llm_model_repository = MagicMock()
    perm_repo = MagicMock()
    logger = MagicMock()

    default_model = _make_default_llm_model()
    llm_model_repository.find_by_id = AsyncMock(return_value=default_model)
    llm_model_repository.find_default = AsyncMock(return_value=default_model)

    async def _find_perm(name, req_id):
        if perm_by_name:
            return perm_by_name.get(name)
        return None

    perm_repo.find_by_collection_name = AsyncMock(side_effect=_find_perm)

    async def _save_passthrough(agent, req_id):
        return agent

    repository.save = AsyncMock(side_effect=_save_passthrough)

    kb_repo = None
    if with_kb_repo:
        kb_repo = MagicMock()

        async def _find_kb(kb_id, req_id):
            return (kb_by_id or {}).get(kb_id)

        kb_repo.find_by_id = AsyncMock(side_effect=_find_kb)

    dept_repo = None
    if user_dept_ids is not None:
        dept_repo = MagicMock()
        memberships = [
            MagicMock(department_id=dept_id) for dept_id in user_dept_ids
        ]
        dept_repo.find_departments_by_user = AsyncMock(
            return_value=memberships
        )

    use_case = CreateAgentUseCase(
        repository=repository,
        llm_model_repository=llm_model_repository,
        perm_repo=perm_repo,
        logger=logger,
        dept_repo=dept_repo,
        kb_repo=kb_repo,
    )
    return use_case, repository, perm_repo


class TestCreateAgentUseCase:
    @pytest.mark.asyncio
    async def test_execute_returns_create_agent_response(self):
        use_case, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="AI 관련 뉴스 검색하고 엑셀로 저장하는 에이전트 만들어줘",
            name="AI 뉴스 수집기",
            user_id="user-1",
            system_prompt=PROMPT,
        )
        result = await use_case.execute(request, "req-1")
        assert isinstance(result, CreateAgentResponse)
        assert result.name == "AI 뉴스 수집기"
        assert result.system_prompt == PROMPT

    @pytest.mark.asyncio
    async def test_execute_calls_repository_save(self):
        use_case, repository, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트 요청", name="테스트", user_id="user-1",
            system_prompt=PROMPT,
        )
        await use_case.execute(request, "req-1")
        repository.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_response_contains_tool_ids(self):
        use_case, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트 요청", name="테스트", user_id="user-1",
            system_prompt=PROMPT,
            tool_ids=["internal:tavily_search", "internal:excel_export"],
        )
        result = await use_case.execute(request, "req-1")
        assert set(result.tool_ids) == {"tavily_search", "excel_export"}

    @pytest.mark.asyncio
    async def test_execute_uses_provided_system_prompt(self):
        use_case, repo, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="요청", name="테스트", user_id="user-1",
            system_prompt="사용자가 직접 입력한 지침",
        )
        result = await use_case.execute(request, "req-1")
        assert result.system_prompt == "사용자가 직접 입력한 지침"
        saved = repo.save.call_args[0][0]
        assert saved.system_prompt == "사용자가 직접 입력한 지침"

    @pytest.mark.asyncio
    async def test_execute_allows_zero_tools(self):
        # agent-instruction-required: 도구 미지정 시 워커 0개 순수 대화형 에이전트 생성
        use_case, repo, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="일반 상담 에이전트", name="상담봇", user_id="user-1",
            system_prompt=PROMPT,
        )
        result = await use_case.execute(request, "req-1")
        assert result.tool_ids == []
        assert result.flow_hint == ""
        saved = repo.save.call_args[0][0]
        assert saved.workers == []

    @pytest.mark.asyncio
    async def test_execute_raises_on_empty_system_prompt(self):
        # agent-instruction-required: 빈 지침 거부 (자동생성 제거)
        use_case, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="요청", name="테스트", user_id="user-1",
            system_prompt="",
        )
        with pytest.raises(ValueError, match="비어"):
            await use_case.execute(request, "req-1")

    @pytest.mark.asyncio
    async def test_execute_raises_on_none_system_prompt(self):
        use_case, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="요청", name="테스트", user_id="user-1",
            system_prompt=None,
        )
        with pytest.raises(ValueError, match="비어"):
            await use_case.execute(request, "req-1")

    @pytest.mark.asyncio
    async def test_execute_raises_on_whitespace_system_prompt(self):
        use_case, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="요청", name="테스트", user_id="user-1",
            system_prompt="   \n\t ",
        )
        with pytest.raises(ValueError, match="비어"):
            await use_case.execute(request, "req-1")


class TestVisibilityClamping:
    @pytest.mark.asyncio
    async def test_public_clamped_to_private_by_personal_collection(self):
        perm = _make_perm(CollectionScope.PERSONAL, "my-docs")
        use_case, repo, _ = _make_use_case(perm_by_name={"my-docs": perm})
        request = CreateAgentRequest(
            user_request="테스트", name="테스트", user_id="user-1",
            system_prompt=PROMPT,
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
        use_case, repo, _ = _make_use_case(perm_by_name={"dept-docs": perm})
        request = CreateAgentRequest(
            user_request="테스트", name="테스트", user_id="user-1",
            system_prompt=PROMPT,
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
        use_case, repo, _ = _make_use_case(perm_by_name={"pub-docs": perm})
        request = CreateAgentRequest(
            user_request="테스트", name="테스트", user_id="user-1",
            system_prompt=PROMPT,
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
        use_case, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트", name="테스트", user_id="user-1",
            system_prompt=PROMPT,
            visibility="public",
        )
        result = await use_case.execute(request, "req-1")
        assert result.visibility_clamped is False
        assert result.max_visibility is None

    @pytest.mark.asyncio
    async def test_explicit_tool_configs_clamp_visibility(self):
        """tool_configs로 직접 선택해도 visibility clamping이 동작한다."""
        perm = _make_perm(CollectionScope.PERSONAL, "my-docs")
        use_case, _, _ = _make_use_case(perm_by_name={"my-docs": perm})
        request = CreateAgentRequest(
            user_request="테스트",
            name="테스트 에이전트",
            user_id="user-1",
            system_prompt=PROMPT,
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
        use_case, repo, _ = _make_use_case(perm_by_name={})
        request = CreateAgentRequest(
            user_request="테스트", name="테스트", user_id="user-1",
            system_prompt=PROMPT,
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


class TestKbRagFilter:
    """kb-rag-filter D1/D3/D7 — KB 검증·컬렉션 고정·scope clamp."""

    @staticmethod
    def _request(
        visibility: str = "public",
        kb_id: str = "kb-1",
        department_id: str | None = None,
    ):
        # user_id "1" == 테스트 KB 기본 owner_id(1) — 소유자 정상 흐름 재현
        return CreateAgentRequest(
            user_request="테스트",
            name="KB 에이전트",
            user_id="1",
            system_prompt=PROMPT,
            visibility=visibility,
            department_id=department_id,
            tool_configs={
                "internal:internal_document_search": RagToolConfigRequest(
                    kb_id=kb_id
                )
            },
        )

    @pytest.mark.asyncio
    async def test_personal_kb_clamps_visibility_to_private(self):
        kb = _make_kb("kb-1", CollectionScope.PERSONAL)
        use_case, _, _ = _make_use_case(kb_by_id={"kb-1": kb})
        result = await use_case.execute(self._request(), "req-1")
        assert result.visibility == "private"
        assert result.visibility_clamped is True

    @pytest.mark.asyncio
    async def test_department_kb_clamps_public_to_department(self):
        kb = _make_kb(
            "kb-1", CollectionScope.DEPARTMENT, department_id="dept-1"
        )
        use_case, _, _ = _make_use_case(
            kb_by_id={"kb-1": kb}, user_dept_ids=["dept-1"]
        )
        result = await use_case.execute(
            self._request(department_id="dept-1"), "req-1"
        )
        assert result.visibility == "department"
        assert result.visibility_clamped is True

    @pytest.mark.asyncio
    async def test_public_kb_no_clamp(self):
        kb = _make_kb("kb-1", CollectionScope.PUBLIC)
        use_case, _, _ = _make_use_case(kb_by_id={"kb-1": kb})
        result = await use_case.execute(self._request(), "req-1")
        assert result.visibility == "public"
        assert result.visibility_clamped is False

    @pytest.mark.asyncio
    async def test_canonicalizes_collection_from_kb(self):
        """D1: 저장된 tool_config.collection_name == KB의 물리 컬렉션."""
        kb = _make_kb("kb-1", CollectionScope.PUBLIC, "admin-coll-01")
        use_case, repo, _ = _make_use_case(kb_by_id={"kb-1": kb})
        await use_case.execute(self._request(), "req-1")
        saved = repo.save.call_args[0][0]
        rag_worker = next(
            w for w in saved.workers
            if w.tool_id == "internal_document_search"
        )
        assert rag_worker.tool_config["kb_id"] == "kb-1"
        assert rag_worker.tool_config["collection_name"] == "admin-coll-01"

    @pytest.mark.asyncio
    async def test_kb_worker_skips_collection_scope_lookup(self):
        """D7: kb_id 워커의 물리 컬렉션은 perm 조회 대상이 아님 (KB scope가 지배)."""
        kb = _make_kb("kb-1", CollectionScope.PUBLIC, "admin-coll-01")
        use_case, _, perm_repo = _make_use_case(kb_by_id={"kb-1": kb})
        result = await use_case.execute(self._request(), "req-1")
        perm_repo.find_by_collection_name.assert_not_awaited()
        assert result.visibility == "public"

    @pytest.mark.asyncio
    async def test_unknown_kb_raises(self):
        """D3: 미존재/soft-delete된 kb_id → ValueError."""
        use_case, _, _ = _make_use_case(kb_by_id={})
        with pytest.raises(ValueError, match="Knowledge base not found"):
            await use_case.execute(self._request(kb_id="kb-missing"), "req-1")

    @pytest.mark.asyncio
    async def test_other_users_personal_kb_raises_permission_error(self):
        """D3(Act-1 G1): 타인 PERSONAL KB 배선 시도 → PermissionError(403)."""
        kb = _make_kb("kb-1", CollectionScope.PERSONAL, owner_id=2)
        use_case, _, _ = _make_use_case(kb_by_id={"kb-1": kb})
        with pytest.raises(PermissionError, match="No read access"):
            await use_case.execute(self._request(), "req-1")

    @pytest.mark.asyncio
    async def test_department_kb_non_member_raises_permission_error(self):
        """D3(Act-1 G1): 미소속 부서 KB 배선 시도 → PermissionError(403)."""
        kb = _make_kb(
            "kb-1", CollectionScope.DEPARTMENT,
            owner_id=2, department_id="dept-9",
        )
        use_case, _, _ = _make_use_case(
            kb_by_id={"kb-1": kb}, user_dept_ids=["dept-1"]
        )
        with pytest.raises(PermissionError, match="No read access"):
            await use_case.execute(
                self._request(department_id="dept-1"), "req-1"
            )

    @pytest.mark.asyncio
    async def test_admin_can_wire_other_users_personal_kb(self):
        """D3(Act-1 G1): admin은 타인 KB 배선 가능 — clamp은 여전히 적용."""
        kb = _make_kb("kb-1", CollectionScope.PERSONAL, owner_id=2)
        use_case, _, _ = _make_use_case(kb_by_id={"kb-1": kb})
        result = await use_case.execute(
            self._request(), "req-1", viewer_role="admin"
        )
        assert result.visibility == "private"
        assert result.visibility_clamped is True

    @pytest.mark.asyncio
    async def test_kb_id_without_repo_raises(self):
        """D7: kb_id 지정 + kb_repo 미주입 → 조용한 skip 금지, 명시적 에러."""
        use_case, _, _ = _make_use_case(with_kb_repo=False)
        with pytest.raises(ValueError, match="kb_repo"):
            await use_case.execute(self._request(), "req-1")

    @pytest.mark.asyncio
    async def test_without_kb_id_existing_flow_unchanged(self):
        """FR-06: kb_id 미설정이면 kb_repo 미호출 + 기존 컬렉션 clamp 동작."""
        perm = _make_perm(CollectionScope.PERSONAL, "my-docs")
        kb = _make_kb("kb-1", CollectionScope.PUBLIC)
        use_case, _, _ = _make_use_case(
            perm_by_name={"my-docs": perm}, kb_by_id={"kb-1": kb}
        )
        request = CreateAgentRequest(
            user_request="테스트", name="테스트", user_id="user-1",
            system_prompt=PROMPT, visibility="public",
            tool_configs={
                "internal:internal_document_search": RagToolConfigRequest(
                    collection_name="my-docs"
                )
            },
        )
        result = await use_case.execute(request, "req-1")
        assert result.visibility == "private"
        assert result.visibility_clamped is True


class TestExplicitToolSelection:
    """tool_configs 명시적 도구 선택 테스트."""

    @pytest.mark.asyncio
    async def test_tool_configs_normalizes_prefix(self):
        """'internal:internal_document_search' → 'internal_document_search'."""
        use_case, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트",
            name="테스트 에이전트",
            user_id="user-1",
            system_prompt=PROMPT,
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
        use_case, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트",
            name="테스트 에이전트",
            user_id="user-1",
            system_prompt=PROMPT,
            tool_configs={
                "internal:nonexistent_tool": RagToolConfigRequest()
            },
        )
        with pytest.raises(ValueError, match="Unknown tool_id"):
            await use_case.execute(request, "req-1")

    @pytest.mark.asyncio
    async def test_no_tools_creates_zero_worker_agent(self):
        """tool_configs/tool_ids 없을 때 워커 0개로 생성 (자동선택 없음)."""
        use_case, repo, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트 요청",
            name="테스트",
            user_id="user-1",
            system_prompt=PROMPT,
        )
        result = await use_case.execute(request, "req-1")
        assert result.tool_ids == []
        saved = repo.save.call_args[0][0]
        assert saved.workers == []

    @pytest.mark.asyncio
    async def test_tool_config_applied_to_worker(self):
        """tool_configs의 설정이 WorkerDefinition.tool_config에 적용된다."""
        use_case, repo, _ = _make_use_case()
        config = RagToolConfigRequest(
            collection_name="my-docs",
            top_k=10,
            search_mode="vector_only",
        )
        request = CreateAgentRequest(
            user_request="테스트",
            name="테스트 에이전트",
            user_id="user-1",
            system_prompt=PROMPT,
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
    async def test_tool_ids_builds_skeleton_with_selected_tools(self):
        """선택한 도구가 그대로 워커로 구성된다."""
        use_case, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트",
            name="테스트 에이전트",
            user_id="user-1",
            system_prompt=PROMPT,
            tool_ids=["internal:tavily_search", "internal:python_code_executor"],
        )
        result = await use_case.execute(request, "req-1")
        assert set(result.tool_ids) == {"tavily_search", "python_code_executor"}

    @pytest.mark.asyncio
    async def test_tool_ids_prefix_normalized(self):
        """'internal:tavily_search' → 'tavily_search'."""
        use_case, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트",
            name="테스트 에이전트",
            user_id="user-1",
            system_prompt=PROMPT,
            tool_ids=["internal:tavily_search"],
        )
        result = await use_case.execute(request, "req-1")
        assert result.tool_ids == ["tavily_search"]

    @pytest.mark.asyncio
    async def test_tool_ids_with_rag_config_merges_config(self):
        """tool_ids + 매칭되는 tool_configs 시 해당 워커에 설정 주입, 나머지는 None."""
        use_case, repo, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트",
            name="테스트 에이전트",
            user_id="user-1",
            system_prompt=PROMPT,
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
    async def test_empty_tool_ids_creates_zero_worker(self):
        """tool_ids 빈 리스트 시 워커 0개로 생성 (자동선택 없음)."""
        use_case, repo, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트 요청",
            name="테스트",
            user_id="user-1",
            system_prompt=PROMPT,
            tool_ids=[],
        )
        result = await use_case.execute(request, "req-1")
        assert result.tool_ids == []
        saved = repo.save.call_args[0][0]
        assert saved.workers == []

    @pytest.mark.asyncio
    async def test_unknown_tool_id_in_tool_ids_raises(self):
        """MCP 레지스트리 미주입 상태에서 mcp_* tool_id → ValueError."""
        use_case, _, _ = _make_use_case()
        request = CreateAgentRequest(
            user_request="테스트",
            name="테스트 에이전트",
            user_id="user-1",
            system_prompt=PROMPT,
            tool_ids=["mcp:server-1:some_tool"],
        )
        with pytest.raises(ValueError, match="Unknown tool_id"):
            await use_case.execute(request, "req-1")


def _make_sub_agent(
    agent_id: str = "sub-agent-1",
    user_id: str = "user-1",
    name: str = "서브 에이전트",
    visibility: str = "private",
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
        visibility=visibility,
        created_at=now,
        updated_at=now,
    )


def _make_use_case_with_sub_agent(
    sub_agent: AgentDefinition | None = None,
    is_subscribed: bool = False,
):
    repository = MagicMock()
    llm_model_repository = MagicMock()
    perm_repo = MagicMock()
    logger = MagicMock()
    subscription_repo = MagicMock()

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
            system_prompt=PROMPT,
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
            system_prompt=PROMPT,
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
            system_prompt=PROMPT,
            sub_agent_configs=[
                SubAgentConfigRequest(ref_agent_id="sub-1")
            ],
        )
        with pytest.raises(ValueError, match="서브 에이전트를 찾을 수 없습니다"):
            await use_case.execute(request, "req-1")

    @pytest.mark.asyncio
    async def test_sub_agent_access_denied_for_private_other_user(self):
        """타인 소유 비공개(private) 에이전트는 사용 불가 (가시성 기반)."""
        sub = _make_sub_agent("sub-1", user_id="other-user", visibility="private")
        use_case, _, _ = _make_use_case_with_sub_agent(sub_agent=sub)
        request = CreateAgentRequest(
            user_request="테스트",
            name="복합 에이전트",
            user_id="user-1",
            system_prompt=PROMPT,
            sub_agent_configs=[
                SubAgentConfigRequest(ref_agent_id="sub-1")
            ],
        )
        with pytest.raises(PermissionError, match="사용 권한이 없습니다"):
            await use_case.execute(request, "req-1")

    @pytest.mark.asyncio
    async def test_sub_agent_access_allowed_for_public_other_user(self):
        """타인 소유라도 전체공개(public) 에이전트는 구독 없이 사용 가능."""
        sub = _make_sub_agent(
            "sub-1", user_id="other-user", name="공개봇", visibility="public"
        )
        use_case, _, _ = _make_use_case_with_sub_agent(sub_agent=sub)
        request = CreateAgentRequest(
            user_request="테스트",
            name="복합 에이전트",
            user_id="user-1",
            system_prompt=PROMPT,
            sub_agent_configs=[
                SubAgentConfigRequest(ref_agent_id="sub-1")
            ],
        )
        result = await use_case.execute(request, "req-1")
        assert result.has_sub_agents is True

    @pytest.mark.asyncio
    async def test_mixed_tool_and_sub_agent_workers(self):
        """도구 + 서브 에이전트 혼합 모드 (도구는 tool_ids로 명시)."""
        sub = _make_sub_agent("sub-1", user_id="user-1", name="분석봇")
        use_case, repo, _ = _make_use_case_with_sub_agent(sub_agent=sub)
        request = CreateAgentRequest(
            user_request="테스트",
            name="복합 에이전트",
            user_id="user-1",
            system_prompt=PROMPT,
            tool_ids=["internal:tavily_search"],
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
        """sub_agent_configs 없을 때 기존 동작 유지 (tool_ids로 도구 지정)."""
        use_case, _, _ = _make_use_case_with_sub_agent(sub_agent=None)
        request = CreateAgentRequest(
            user_request="테스트",
            name="일반 에이전트",
            user_id="user-1",
            system_prompt=PROMPT,
            tool_ids=["internal:tavily_search"],
        )
        result = await use_case.execute(request, "req-1")
        assert result.has_sub_agents is False
        assert all(w.worker_type == "tool" for w in result.workers)


class TestCreateAgentSkillSync:
    """agent-skill-toggle: 등록 시점 부착 스킬 동기화."""

    @pytest.mark.asyncio
    async def test_skill_ids_trigger_sync(self):
        use_case, _, _ = _make_use_case()
        use_case._skill_sync = MagicMock()
        use_case._skill_sync.sync = AsyncMock()
        request = CreateAgentRequest(
            user_request="뉴스 수집기", name="A", user_id="user-1",
            system_prompt=PROMPT,
            skill_ids=["s1", "s2"],
        )
        await use_case.execute(request, "req-1", viewer_role="admin")
        use_case._skill_sync.sync.assert_awaited_once()
        _, kwargs = use_case._skill_sync.sync.call_args
        args = use_case._skill_sync.sync.call_args.args
        assert args[1] == ["s1", "s2"]           # desired_skill_ids
        assert kwargs["viewer_user_id"] == "user-1"
        assert kwargs["viewer_role"] == "admin"

    @pytest.mark.asyncio
    async def test_no_skill_ids_skips_sync(self):
        use_case, _, _ = _make_use_case()
        use_case._skill_sync = MagicMock()
        use_case._skill_sync.sync = AsyncMock()
        request = CreateAgentRequest(
            user_request="뉴스 수집기", name="A", user_id="user-1",
            system_prompt=PROMPT,
        )
        await use_case.execute(request, "req-1")
        use_case._skill_sync.sync.assert_not_awaited()
