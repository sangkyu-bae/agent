"""UpdateAgentUseCase 도구 편집 — agent-update-tool-editing D §8.2 (T-01~T-18).

수정 경로가 도구 워커를 목표 상태로 재구성한다:
재구성 → 종속정리 → scope clamp → 정책검증 → 문서/발표자료 바인딩 → save.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.application.agent_builder.schemas import (
    PresentationGeneratorConfigRequest,
    RagToolConfigRequest,
    SubAgentConfigRequest,
    UpdateAgentRequest,
)
from src.application.agent_builder.update_agent_use_case import UpdateAgentUseCase
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.knowledge_base.entities import KnowledgeBase
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType
from src.domain.tool_catalog.entity import ToolCatalogEntry

MCP_SERVER_ID = "11111111-2222-3333-4444-555555555555"
MCP_TOOL_ID = f"mcp:{MCP_SERVER_ID}:fetch"


def _tool(tool_id: str, sort_order: int = 0, tool_config: dict | None = None):
    return WorkerDefinition(
        tool_id=tool_id,
        worker_id=f"{tool_id}_worker",
        description=f"desc-{tool_id}",
        sort_order=sort_order,
        tool_config=tool_config,
    )


def _sub(ref_agent_id: str = "child-1", sort_order: int = 9):
    return WorkerDefinition(
        tool_id="",
        worker_id=f"sub_{ref_agent_id}",
        description="서브에이전트",
        sort_order=sort_order,
        worker_type="sub_agent",
        ref_agent_id=ref_agent_id,
    )


def _make_agent(
    workers: list[WorkerDefinition] | None = None,
    visibility: str = "private",
) -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id=str(uuid.uuid4()),
        user_id="1",
        name="원래 이름",
        description="설명",
        system_prompt="원래 프롬프트",
        flow_hint="힌트",
        workers=workers if workers is not None else [_tool("tavily_search")],
        llm_model_id="model-1",
        status="active",
        created_at=now,
        updated_at=now,
        visibility=visibility,
    )


def _mcp_registration(is_active: bool = True) -> MCPServerRegistration:
    now = datetime.now(timezone.utc)
    return MCPServerRegistration(
        id=MCP_SERVER_ID,
        user_id="1",
        name="테스트 MCP 서버",
        description="MCP 서버 설명",
        endpoint="https://mcp.example.com",
        transport=MCPTransportType.STREAMABLE_HTTP,
        input_schema=None,
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )


def _builtin(tool_id: str) -> ToolCatalogEntry:
    return ToolCatalogEntry(
        id=f"tc-{tool_id}", tool_id=tool_id, source="internal",
        name=tool_id, description=f"desc-{tool_id}",
        mcp_server_id=None, is_active=True, is_builtin=True,
    )


def _make_use_case(
    agent: AgentDefinition,
    builtins: list[ToolCatalogEntry] | None = None,
    mcp_active: bool = True,
    with_mcp_repo: bool = True,
    kb_by_id: dict[str, KnowledgeBase] | None = None,
    active_template=None,
    active_generation_type=None,
):
    repository = MagicMock()
    repository.find_by_id = AsyncMock(return_value=agent)
    repository.update = AsyncMock(side_effect=lambda a, rid: a)

    perm_repo = MagicMock()
    perm_repo.find_by_collection_name = AsyncMock(return_value=None)

    kb_repo = MagicMock()
    kb_repo.find_by_id = AsyncMock(
        side_effect=lambda kb_id, rid: (kb_by_id or {}).get(kb_id)
    )

    tool_catalog_repo = MagicMock()
    tool_catalog_repo.list_builtin = AsyncMock(return_value=builtins or [])
    tool_catalog_repo.find_by_tool_id = AsyncMock(return_value=None)

    mcp_server_repo = None
    if with_mcp_repo:
        mcp_server_repo = MagicMock()
        mcp_server_repo.find_by_id = AsyncMock(
            return_value=_mcp_registration(mcp_active)
        )

    template_repo = MagicMock()
    template_repo.find_active_by_agent_worker = AsyncMock(
        return_value=active_template
    )
    template_repo.soft_delete = AsyncMock()

    gen_type_repo = MagicMock()
    gen_type_repo.find_active_by_agent_worker = AsyncMock(
        return_value=active_generation_type
    )
    gen_type_repo.soft_delete = AsyncMock()

    use_case = UpdateAgentUseCase(
        repository=repository,
        perm_repo=perm_repo,
        logger=MagicMock(),
        kb_repo=kb_repo,
        tool_catalog_repo=tool_catalog_repo,
        mcp_server_repo=mcp_server_repo,
        document_template_repo=template_repo,
        document_generation_type_repo=gen_type_repo,
    )
    return use_case, repository, template_repo, gen_type_repo


def _saved_workers(repository) -> list[WorkerDefinition]:
    return repository.update.call_args[0][0].workers


def _tool_ids(repository) -> list[str]:
    return [
        w.tool_id for w in _saved_workers(repository) if w.worker_type == "tool"
    ]


# --- T-01 무회귀 ---------------------------------------------------------


@pytest.mark.asyncio
async def test_t01_omitting_tool_ids_leaves_workers_untouched():
    agent = _make_agent([_tool("tavily_search"), _tool("excel_export", 1)])
    use_case, repository, _, _ = _make_use_case(agent)

    await use_case.execute(agent.id, UpdateAgentRequest(name="새 이름"), "req-1")

    assert _tool_ids(repository) == ["tavily_search", "excel_export"]


# --- T-02 원 결함 해소 ---------------------------------------------------


@pytest.mark.asyncio
async def test_t02_adding_presentation_generator_with_config_succeeds():
    """원 결함: 워커가 없어 422 였던 경로가 재구성 덕분에 성공한다."""
    agent = _make_agent([_tool("tavily_search")])
    use_case, repository, _, _ = _make_use_case(agent)

    await use_case.execute(
        agent.id,
        UpdateAgentRequest(
            tool_ids=["internal:tavily_search", "internal:presentation_generator"],
            presentation_generator=PresentationGeneratorConfigRequest(
                blueprint_id="bp-1", max_slides=12
            ),
        ),
        "req-1",
    )

    saved = {w.tool_id: w for w in _saved_workers(repository)}
    assert "presentation_generator" in saved
    assert saved["presentation_generator"].tool_config["blueprint_id"] == "bp-1"


# --- T-03 제거 / T-05 순서 -----------------------------------------------


@pytest.mark.asyncio
async def test_t03_removed_tool_disappears_and_sort_order_is_compacted():
    agent = _make_agent(
        [_tool("tavily_search"), _tool("excel_export", 1), _tool("wiki_read", 2)]
    )
    use_case, repository, _, _ = _make_use_case(agent)

    await use_case.execute(
        agent.id,
        UpdateAgentRequest(tool_ids=["internal:tavily_search", "internal:wiki_read"]),
        "req-1",
    )

    assert _tool_ids(repository) == ["tavily_search", "wiki_read"]
    assert [w.sort_order for w in _saved_workers(repository)] == [0, 1]


# --- T-04 / T-05 config 승계 ---------------------------------------------


@pytest.mark.asyncio
async def test_t04_kept_tool_inherits_existing_config_when_not_sent():
    rag = _tool(
        "internal_document_search",
        tool_config={"top_k": 9, "kb_id": None, "collection_name": "coll-a"},
    )
    agent = _make_agent([rag])
    use_case, repository, _, _ = _make_use_case(agent)

    await use_case.execute(
        agent.id,
        UpdateAgentRequest(
            tool_ids=["internal:internal_document_search", "internal:tavily_search"]
        ),
        "req-1",
    )

    saved = {w.tool_id: w for w in _saved_workers(repository)}
    assert saved["internal_document_search"].tool_config["top_k"] == 9
    assert saved["internal_document_search"].tool_config["collection_name"] == "coll-a"


@pytest.mark.asyncio
async def test_t05_sent_config_overrides_existing():
    rag = _tool("internal_document_search", tool_config={"top_k": 9})
    agent = _make_agent([rag])
    use_case, repository, _, _ = _make_use_case(agent)

    await use_case.execute(
        agent.id,
        UpdateAgentRequest(
            tool_ids=["internal:internal_document_search"],
            tool_configs={
                "internal:internal_document_search": RagToolConfigRequest(top_k=3)
            },
        ),
        "req-1",
    )

    saved = {w.tool_id: w for w in _saved_workers(repository)}
    assert saved["internal_document_search"].tool_config["top_k"] == 3


# --- T-06 / T-07 종속 정리 -----------------------------------------------


@pytest.mark.asyncio
async def test_t06_removing_document_generator_soft_deletes_generation_type():
    agent = _make_agent([_tool("tavily_search"), _tool("document_generator", 1)])
    existing = MagicMock()
    existing.id = "gt-1"
    use_case, _, _, gen_type_repo = _make_use_case(
        agent, active_generation_type=existing
    )

    await use_case.execute(
        agent.id, UpdateAgentRequest(tool_ids=["internal:tavily_search"]), "req-1"
    )

    gen_type_repo.soft_delete.assert_awaited_once_with("gt-1", "req-1")


@pytest.mark.asyncio
async def test_t07_removing_document_extractor_soft_deletes_template():
    agent = _make_agent([_tool("tavily_search"), _tool("document_extractor", 1)])
    existing = MagicMock()
    existing.id = "tpl-1"
    use_case, _, template_repo, _ = _make_use_case(agent, active_template=existing)

    await use_case.execute(
        agent.id, UpdateAgentRequest(tool_ids=["internal:tavily_search"]), "req-1"
    )

    template_repo.soft_delete.assert_awaited_once_with("tpl-1", "req-1")


@pytest.mark.asyncio
async def test_kept_document_generator_is_not_soft_deleted():
    agent = _make_agent([_tool("document_generator")])
    existing = MagicMock()
    existing.id = "gt-1"
    use_case, _, _, gen_type_repo = _make_use_case(
        agent, active_generation_type=existing
    )

    await use_case.execute(
        agent.id,
        UpdateAgentRequest(tool_ids=["internal:document_generator"]),
        "req-1",
    )

    gen_type_repo.soft_delete.assert_not_awaited()


# --- T-08 서브에이전트 보존 ----------------------------------------------


@pytest.mark.asyncio
async def test_t08_sub_agents_survive_tool_change_and_move_after_tools():
    agent = _make_agent([_tool("tavily_search"), _sub()])
    use_case, repository, _, _ = _make_use_case(agent)

    await use_case.execute(
        agent.id,
        UpdateAgentRequest(
            tool_ids=["internal:excel_export", "internal:wiki_read"]
        ),
        "req-1",
    )

    saved = _saved_workers(repository)
    assert [w.worker_type for w in saved] == ["tool", "tool", "sub_agent"]
    assert [w.sort_order for w in saved] == [0, 1, 2]


# --- T-09 전부 해제 ------------------------------------------------------


@pytest.mark.asyncio
async def test_t09_empty_tool_ids_clears_user_tools_but_keeps_builtins():
    agent = _make_agent([_tool("tavily_search")])
    use_case, repository, _, _ = _make_use_case(
        agent, builtins=[_builtin("internal:wiki_read")]
    )

    await use_case.execute(agent.id, UpdateAgentRequest(tool_ids=[]), "req-1")

    assert _tool_ids(repository) == ["wiki_read"]


# --- T-10 ~ T-14 에러 ----------------------------------------------------


@pytest.mark.asyncio
async def test_t10_unknown_tool_id_raises_value_error():
    agent = _make_agent()
    use_case, _, _, _ = _make_use_case(agent)

    with pytest.raises(ValueError):
        await use_case.execute(
            agent.id, UpdateAgentRequest(tool_ids=["internal:no_such_tool"]), "req-1"
        )


@pytest.mark.asyncio
async def test_t11_mcp_tool_can_be_added():
    agent = _make_agent()
    use_case, repository, _, _ = _make_use_case(agent)

    await use_case.execute(
        agent.id, UpdateAgentRequest(tool_ids=[MCP_TOOL_ID]), "req-1"
    )

    assert _tool_ids(repository) == [MCP_TOOL_ID]


@pytest.mark.asyncio
async def test_t12_inactive_mcp_server_raises_value_error():
    agent = _make_agent()
    use_case, _, _, _ = _make_use_case(agent, mcp_active=False)

    with pytest.raises(ValueError, match="비활성화"):
        await use_case.execute(
            agent.id, UpdateAgentRequest(tool_ids=[MCP_TOOL_ID]), "req-1"
        )


@pytest.mark.asyncio
async def test_t13_missing_mcp_repo_raises_value_error_not_type_error():
    agent = _make_agent()
    use_case, _, _, _ = _make_use_case(agent, with_mcp_repo=False)

    with pytest.raises(ValueError):
        await use_case.execute(
            agent.id, UpdateAgentRequest(tool_ids=[MCP_TOOL_ID]), "req-1"
        )


@pytest.mark.asyncio
async def test_t14_tool_configs_without_tool_ids_is_rejected():
    """원 결함의 형태 — 도구 목록 없이 설정만 오는 요청은 계약 위반."""
    agent = _make_agent()
    use_case, _, _, _ = _make_use_case(agent)

    with pytest.raises(ValueError, match="tool_ids"):
        await use_case.execute(
            agent.id,
            UpdateAgentRequest(
                tool_configs={
                    "internal:internal_document_search": RagToolConfigRequest()
                }
            ),
            "req-1",
        )


# --- T-15 정책 -----------------------------------------------------------


@pytest.mark.asyncio
async def test_t15_exceeding_tool_limit_raises():
    from src.domain.agent_builder.policies import AgentBuilderPolicy

    agent = _make_agent()
    use_case, _, _, _ = _make_use_case(agent)
    too_many = _many_tool_ids(AgentBuilderPolicy.MAX_TOOLS + 1)

    with pytest.raises(ValueError, match="최대"):
        await use_case.execute(
            agent.id, UpdateAgentRequest(tool_ids=too_many), "req-1"
        )


def _many_tool_ids(count: int) -> list[str]:
    """상한 초과 검증용 도구 ID 목록.

    내부 레지스트리 도구 수가 MAX_TOOLS 보다 적을 수 있으므로(상한을 올리면
    바로 그렇게 된다) 모자란 만큼 MCP 개별 도구 ID 로 채운다. 상한 검증은
    도구 출처와 무관하게 워커 총 개수로 이뤄지므로 검증 의도는 동일하다.
    """
    from src.domain.agent_builder.tool_registry import TOOL_REGISTRY

    ids = [f"internal:{t}" for t in TOOL_REGISTRY][:count]
    ids += [f"mcp:{MCP_SERVER_ID}:extra_{i}" for i in range(count - len(ids))]
    return ids


# --- T-16 visibility clamp ----------------------------------------------


@pytest.mark.asyncio
async def test_t16_adding_personal_kb_tool_clamps_public_visibility():
    agent = _make_agent([_tool("tavily_search")], visibility="public")
    kb = KnowledgeBase(
        id="kb-1", name="개인 KB", owner_id=1,
        scope=CollectionScope.PERSONAL, collection_name="kb-coll",
    )
    use_case, repository, _, _ = _make_use_case(agent, kb_by_id={"kb-1": kb})

    res = await use_case.execute(
        agent.id,
        UpdateAgentRequest(
            tool_ids=["internal:internal_document_search"],
            tool_configs={
                "internal:internal_document_search": RagToolConfigRequest(
                    kb_id="kb-1"
                )
            },
        ),
        "req-1",
    )

    assert res.visibility == "private"
    assert res.visibility_clamped is True
    assert repository.update.call_args[0][0].visibility == "private"


@pytest.mark.asyncio
async def test_kb_collection_name_is_canonicalized_on_update():
    """kb-rag-filter D1: kb_id 워커의 collection_name은 KB 물리 컬렉션으로 고정."""
    agent = _make_agent([_tool("tavily_search")])
    kb = KnowledgeBase(
        id="kb-1", name="개인 KB", owner_id=1,
        scope=CollectionScope.PERSONAL, collection_name="kb-coll",
    )
    use_case, repository, _, _ = _make_use_case(agent, kb_by_id={"kb-1": kb})

    await use_case.execute(
        agent.id,
        UpdateAgentRequest(
            tool_ids=["internal:internal_document_search"],
            tool_configs={
                "internal:internal_document_search": RagToolConfigRequest(
                    kb_id="kb-1", collection_name="사용자가-보낸-값"
                )
            },
        ),
        "req-1",
    )

    saved = {w.tool_id: w for w in _saved_workers(repository)}
    assert (
        saved["internal_document_search"].tool_config["collection_name"] == "kb-coll"
    )


@pytest.mark.asyncio
async def test_explicit_visibility_request_is_validated_against_new_workers():
    """명시적 visibility 요청은 clamp 가 아니라 422 거부 (설계 §7)."""
    agent = _make_agent([_tool("tavily_search")])
    kb = KnowledgeBase(
        id="kb-1", name="개인 KB", owner_id=1,
        scope=CollectionScope.PERSONAL, collection_name="kb-coll",
    )
    use_case, _, _, _ = _make_use_case(agent, kb_by_id={"kb-1": kb})

    with pytest.raises(ValueError, match="최대 허용"):
        await use_case.execute(
            agent.id,
            UpdateAgentRequest(
                visibility="public",
                tool_ids=["internal:internal_document_search"],
                tool_configs={
                    "internal:internal_document_search": RagToolConfigRequest(
                        kb_id="kb-1"
                    )
                },
            ),
            "req-1",
        )


# --- T-17 / T-18 ---------------------------------------------------------


@pytest.mark.asyncio
async def test_t17_worker_id_is_deterministic_after_rebuild():
    agent = _make_agent([_tool("document_generator")])
    use_case, repository, _, _ = _make_use_case(agent)

    await use_case.execute(
        agent.id,
        UpdateAgentRequest(
            tool_ids=["internal:document_generator", "internal:tavily_search"]
        ),
        "req-1",
    )

    saved = {w.tool_id: w for w in _saved_workers(repository)}
    assert saved["document_generator"].worker_id == "document_generator_worker"


@pytest.mark.asyncio
async def test_t18_builtin_is_not_injected_twice_when_user_selected():
    agent = _make_agent()
    use_case, repository, _, _ = _make_use_case(
        agent, builtins=[_builtin("internal:wiki_read")]
    )

    await use_case.execute(
        agent.id, UpdateAgentRequest(tool_ids=["internal:wiki_read"]), "req-1"
    )

    assert _tool_ids(repository) == ["wiki_read"]


@pytest.mark.asyncio
async def test_sub_agent_configs_and_tool_ids_together():
    """도구 재구성이 서브에이전트 재구성보다 앞서 sort_order가 어긋나지 않는다."""
    agent = _make_agent([_tool("tavily_search"), _sub("child-1")])
    use_case, repository, _, _ = _make_use_case(agent)
    child = _make_agent()
    child.visibility = "public"
    use_case._sub_agent_builder.build = AsyncMock(
        return_value=[_sub("child-2", 0)]
    )

    await use_case.execute(
        agent.id,
        UpdateAgentRequest(
            tool_ids=["internal:excel_export", "internal:wiki_read"],
            sub_agent_configs=[
                SubAgentConfigRequest(ref_agent_id="child-2", description="")
            ],
        ),
        "req-1",
    )

    saved = _saved_workers(repository)
    assert [w.worker_type for w in saved] == ["tool", "tool", "sub_agent"]
    assert saved[2].sort_order == 2


# --- wiki-guided-routing D5: Tool Guidelines 섹션 재생성 -------------------


_PROMPT = (
    "리드 문단\n\n"
    "## Tool Guidelines\n"
    "- Tavily 웹 검색 (internal:tavily_search): 옛 설명\n\n"
    "## Important Notes\n- 사용자가 편집한 줄"
)


def _saved_prompt(repository) -> str:
    return repository.update.call_args[0][0].system_prompt


@pytest.mark.asyncio
async def test_d5_tool_change_regenerates_tool_guidelines_section_only():
    agent = _make_agent([_tool("tavily_search")])
    agent.system_prompt = _PROMPT
    use_case, repository, _, _ = _make_use_case(agent)

    await use_case.execute(
        agent.id,
        UpdateAgentRequest(tool_ids=["internal:tavily_search", "internal:excel_export"]),
        "req-1",
    )

    prompt = _saved_prompt(repository)
    assert "## Tool Guidelines" in prompt
    assert "(internal:excel_export)" in prompt
    assert "(internal:tavily_search)" in prompt
    assert "옛 설명" not in prompt
    assert prompt.startswith("리드 문단\n\n")
    assert prompt.endswith("## Important Notes\n- 사용자가 편집한 줄")


@pytest.mark.asyncio
async def test_d5_removed_tool_disappears_from_guidelines():
    agent = _make_agent([_tool("tavily_search"), _tool("excel_export", 1)])
    agent.system_prompt = _PROMPT
    use_case, repository, _, _ = _make_use_case(agent)

    await use_case.execute(
        agent.id, UpdateAgentRequest(tool_ids=["internal:excel_export"]), "req-1"
    )

    prompt = _saved_prompt(repository)
    assert "(internal:tavily_search)" not in prompt
    assert "(internal:excel_export)" in prompt


@pytest.mark.asyncio
async def test_d5_builtin_and_mcp_tools_included_with_catalog_ids():
    agent = _make_agent([_tool("tavily_search")])
    agent.system_prompt = _PROMPT
    use_case, repository, _, _ = _make_use_case(agent, builtins=[_builtin("wiki_read")])

    await use_case.execute(
        agent.id, UpdateAgentRequest(tool_ids=["internal:tavily_search", MCP_TOOL_ID]), "req-1"
    )

    prompt = _saved_prompt(repository)
    assert f"- fetch ({MCP_TOOL_ID}):" in prompt
    assert "(internal:wiki_read)" in prompt


@pytest.mark.asyncio
async def test_d5_prompt_without_heading_is_untouched():
    agent = _make_agent([_tool("tavily_search")])
    agent.system_prompt = "사용자가 도구 섹션을 지운 프롬프트"
    use_case, repository, _, _ = _make_use_case(agent)

    await use_case.execute(
        agent.id, UpdateAgentRequest(tool_ids=["internal:excel_export"]), "req-1"
    )

    assert _saved_prompt(repository) == "사용자가 도구 섹션을 지운 프롬프트"


@pytest.mark.asyncio
async def test_d5_request_prompt_wins_when_sent_with_tool_ids():
    agent = _make_agent([_tool("tavily_search")])
    agent.system_prompt = _PROMPT
    use_case, repository, _, _ = _make_use_case(agent)

    await use_case.execute(
        agent.id,
        UpdateAgentRequest(
            system_prompt="새 리드\n\n## Tool Guidelines\n- 임시\n\n## Workflow\n1. 단계",
            tool_ids=["internal:excel_export"],
        ),
        "req-1",
    )

    prompt = _saved_prompt(repository)
    assert prompt.startswith("새 리드\n\n## Tool Guidelines\n")
    assert "(internal:excel_export)" in prompt and "- 임시" not in prompt
    assert prompt.endswith("## Workflow\n1. 단계")


@pytest.mark.asyncio
async def test_d5_no_tool_ids_leaves_prompt_untouched():
    agent = _make_agent([_tool("tavily_search")])
    agent.system_prompt = _PROMPT
    use_case, repository, _, _ = _make_use_case(agent)

    await use_case.execute(agent.id, UpdateAgentRequest(name="새 이름"), "req-1")

    assert _saved_prompt(repository) == _PROMPT
