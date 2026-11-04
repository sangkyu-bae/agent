"""UpdateAgentUseCase 도구 권한 테스트 (tool-access-control FR-06·07, Design §8.2 L1-10·11).

결정: 기존 정의에 있던 도구는 권한과 무관하게 유지, 새로 추가한 도구만 검증.
빌트인도 같은 규칙 — 원래 있던 빌트인은 유지, 새로 들어오며 불허인 빌트인은 제외.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.schemas import UpdateAgentRequest
from src.application.agent_builder.update_agent_use_case import UpdateAgentUseCase
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.domain.tool_access.exceptions import ToolAccessDeniedError
from src.domain.tool_access.value_objects import ToolAccessSet
from src.domain.tool_catalog.entity import ToolCatalogEntry


def _tool(tool_id: str) -> WorkerDefinition:
    return WorkerDefinition(tool_id=tool_id, worker_id=f"{tool_id}_worker", description="d")


def _agent(tool_ids) -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id=str(uuid.uuid4()), user_id="1", name="n", description="d",
        system_prompt="원래 프롬프트", flow_hint="h",
        workers=[_tool(t) for t in tool_ids], llm_model_id="m", status="active",
        created_at=now, updated_at=now, visibility="private",
    )


def _builtin(tool_id: str) -> ToolCatalogEntry:
    return ToolCatalogEntry(
        id=f"tc-{tool_id}", tool_id=tool_id, source="internal", name=tool_id,
        description="d", is_active=True, is_builtin=True,
    )


def _use_case(agent, access: ToolAccessSet | None, builtins=()):
    repository = MagicMock()
    repository.find_by_id = AsyncMock(return_value=agent)
    repository.update = AsyncMock(side_effect=lambda a, rid: a)
    perm = MagicMock()
    perm.find_by_collection_name = AsyncMock(return_value=None)
    catalog = MagicMock()
    catalog.list_builtin = AsyncMock(return_value=list(builtins))
    catalog.list_active = AsyncMock(return_value=[])
    catalog.find_by_tool_id = AsyncMock(return_value=None)
    resolver = None
    if access is not None:
        resolver = MagicMock()
        resolver.for_user_id = AsyncMock(return_value=access)
    uc = UpdateAgentUseCase(
        repository=repository, perm_repo=perm, logger=MagicMock(),
        tool_catalog_repo=catalog, tool_access_resolver=resolver,
    )
    return uc, repository, resolver


def _saved(repository) -> list[str]:
    return [w.tool_id for w in repository.update.call_args.args[0].workers if w.worker_type == "tool"]


ONLY_EXCEL = ToolAccessSet(is_admin=False, allowed=frozenset({"internal:excel_export"}))


async def test_existing_denied_tool_kept_when_saving_same_tools():
    agent = _agent(["python_code_executor"])
    uc, repo, resolver = _use_case(agent, ONLY_EXCEL)
    await uc.execute(
        agent.id, UpdateAgentRequest(tool_ids=["internal:python_code_executor", "internal:excel_export"]),
        "rid", viewer_user_id="1",
    )
    assert sorted(_saved(repo)) == ["excel_export", "python_code_executor"]
    resolver.for_user_id.assert_awaited_once_with("1", "rid")


async def test_adding_denied_tool_rejected():
    agent = _agent(["excel_export"])
    uc, repo, _ = _use_case(agent, ONLY_EXCEL)
    with pytest.raises(ToolAccessDeniedError) as ei:
        await uc.execute(
            agent.id,
            UpdateAgentRequest(tool_ids=["internal:excel_export", "internal:python_code_executor"]),
            "rid", viewer_user_id="1",
        )
    assert ei.value.tool_ids == ("internal:python_code_executor",)
    repo.update.assert_not_awaited()


async def test_prompt_only_edit_skips_tool_check():
    agent = _agent(["python_code_executor"])
    uc, repo, resolver = _use_case(agent, ToolAccessSet.deny_all())
    await uc.execute(agent.id, UpdateAgentRequest(system_prompt="새 프롬프트"), "rid", viewer_user_id="1")
    assert _saved(repo) == ["python_code_executor"]
    resolver.for_user_id.assert_not_awaited()


async def test_editor_defaults_to_owner_when_viewer_missing():
    agent = _agent(["excel_export"])
    uc, _, resolver = _use_case(agent, ONLY_EXCEL)
    await uc.execute(agent.id, UpdateAgentRequest(tool_ids=["internal:excel_export"]), "rid")
    resolver.for_user_id.assert_awaited_once_with("1", "rid")


async def test_previous_builtin_kept_new_denied_builtin_skipped():
    agent = _agent(["excel_export", "wiki_read"])
    uc, repo, _ = _use_case(
        agent, ONLY_EXCEL,
        builtins=[_builtin("internal:wiki_read"), _builtin("internal:python_code_executor")],
    )
    await uc.execute(agent.id, UpdateAgentRequest(tool_ids=["internal:excel_export"]), "rid", viewer_user_id="1")
    assert sorted(_saved(repo)) == ["excel_export", "wiki_read"]


async def test_without_resolver_behaves_as_before():
    agent = _agent(["excel_export"])
    uc, repo, _ = _use_case(agent, None)
    await uc.execute(
        agent.id, UpdateAgentRequest(tool_ids=["internal:python_code_executor"]), "rid", viewer_user_id="1"
    )
    assert _saved(repo) == ["python_code_executor"]
