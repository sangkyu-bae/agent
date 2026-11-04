"""CreateAgentUseCase 도구 권한 테스트 (tool-access-control Plan FR-06·07, Design §8.2 L1-9·13)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.create_agent_use_case import CreateAgentUseCase
from src.application.agent_builder.schemas import CreateAgentRequest
from src.domain.llm_model.entity import LlmModel
from src.domain.tool_access.exceptions import ToolAccessDeniedError
from src.domain.tool_access.value_objects import ToolAccessSet
from src.domain.tool_catalog.entity import ToolCatalogEntry


def _model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="m", provider="openai", model_name="gpt-4o", display_name="GPT-4o",
        description=None, api_key_env="OPENAI_API_KEY", max_tokens=1000,
        is_active=True, is_default=True, created_at=now, updated_at=now,
    )


def _builtin(tool_id: str) -> ToolCatalogEntry:
    return ToolCatalogEntry(
        id=f"tc-{tool_id}", tool_id=tool_id, source="internal", name=tool_id,
        description="d", is_active=True, is_builtin=True,
    )


def _use_case(access: ToolAccessSet | None, builtins=()):
    repository = MagicMock()
    repository.save = AsyncMock(side_effect=lambda agent, rid: agent)
    llm = MagicMock()
    llm.find_by_id = AsyncMock(return_value=_model())
    llm.find_default = AsyncMock(return_value=_model())
    perm = MagicMock()
    perm.find_by_collection_name = AsyncMock(return_value=None)
    catalog = MagicMock()
    catalog.list_builtin = AsyncMock(return_value=list(builtins))
    catalog.list_active = AsyncMock(return_value=[])
    resolver = None
    if access is not None:
        resolver = MagicMock()
        resolver.for_user_id = AsyncMock(return_value=access)
    uc = CreateAgentUseCase(
        repository=repository, llm_model_repository=llm, perm_repo=perm,
        logger=MagicMock(), tool_catalog_repo=catalog, tool_access_resolver=resolver,
    )
    return uc, repository, resolver


def _request(**kw) -> CreateAgentRequest:
    base = dict(user_request="r", name="t", user_id="12", system_prompt="지침")
    base.update(kw)
    return CreateAgentRequest(**base)


def _saved_tool_ids(repository) -> list[str]:
    agent = repository.save.call_args.args[0]
    return [w.tool_id for w in agent.workers if w.worker_type == "tool"]


async def test_allowed_tools_are_saved_and_resolver_uses_request_user():
    access = ToolAccessSet(is_admin=False, allowed=frozenset({"internal:excel_export"}))
    uc, repo, resolver = _use_case(access)
    await uc.execute(_request(tool_ids=["internal:excel_export"]), "rid")
    assert _saved_tool_ids(repo) == ["excel_export"]
    resolver.for_user_id.assert_awaited_once_with("12", "rid")


async def test_denied_tool_rejects_whole_create():
    access = ToolAccessSet(is_admin=False, allowed=frozenset({"internal:excel_export"}))
    uc, repo, _ = _use_case(access)
    with pytest.raises(ToolAccessDeniedError) as ei:
        await uc.execute(
            _request(tool_ids=["internal:excel_export", "internal:python_code_executor"]), "rid"
        )
    assert ei.value.tool_ids == ("internal:python_code_executor",)
    repo.save.assert_not_awaited()


async def test_denied_builtin_is_not_injected():
    access = ToolAccessSet(is_admin=False, allowed=frozenset({"internal:wiki_read"}))
    uc, repo, _ = _use_case(
        access, builtins=[_builtin("internal:wiki_read"), _builtin("internal:python_code_executor")]
    )
    await uc.execute(_request(), "rid")
    assert _saved_tool_ids(repo) == ["wiki_read"]


async def test_admin_gets_all_builtins():
    uc, repo, _ = _use_case(
        ToolAccessSet.admin(),
        builtins=[_builtin("internal:wiki_read"), _builtin("internal:python_code_executor")],
    )
    await uc.execute(_request(tool_ids=["internal:python_code_executor"]), "rid")
    assert sorted(_saved_tool_ids(repo)) == ["python_code_executor", "wiki_read"]


async def test_without_resolver_behaves_as_before():
    uc, repo, _ = _use_case(None, builtins=[_builtin("internal:python_code_executor")])
    await uc.execute(_request(tool_ids=["internal:excel_export"]), "rid")
    assert sorted(_saved_tool_ids(repo)) == ["excel_export", "python_code_executor"]


async def test_resolver_failure_blocks_save():
    uc, repo, resolver = _use_case(ToolAccessSet.admin())
    resolver.for_user_id.side_effect = RuntimeError("db down")
    with pytest.raises(RuntimeError):
        await uc.execute(_request(tool_ids=["internal:excel_export"]), "rid")
    repo.save.assert_not_awaited()
