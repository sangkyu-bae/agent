"""ForkAgentUseCase 도구 권한 테스트 (tool-access-control FR-08, Design §8.2 L1-12)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.fork_agent_use_case import ForkAgentUseCase
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.domain.tool_access.value_objects import ToolAccessSet

PROMPT = (
    "역할 설명\n\n## Tool Guidelines\n"
    "- Excel 파일 생성 (internal:excel_export): 엑셀\n"
    "- Python 코드 실행 (internal:python_code_executor): 코드\n"
)


def _w(tool_id: str, worker_type: str = "tool") -> WorkerDefinition:
    return WorkerDefinition(
        tool_id=tool_id, worker_id=f"{tool_id or 'sub'}_w", description=f"{tool_id} 설명",
        worker_type=worker_type, ref_agent_id="child" if worker_type == "sub_agent" else None,
    )


def _source() -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id="src", user_id="owner", name="원본", description="d", system_prompt=PROMPT,
        flow_hint="h",
        workers=[_w("excel_export"), _w("python_code_executor"), _w("", "sub_agent")],
        llm_model_id="m", status="active", visibility="public", temperature=0.3,
        created_at=now, updated_at=now,
    )


def _uc(access: ToolAccessSet | None):
    repo = AsyncMock()
    repo.find_by_id.return_value = _source()
    repo.save.side_effect = lambda agent, rid: agent
    resolver = None
    if access is not None:
        resolver = MagicMock()
        resolver.for_user_id = AsyncMock(return_value=access)
    return ForkAgentUseCase(agent_repo=repo, logger=MagicMock(), tool_access_resolver=resolver), repo, resolver


async def test_denied_tools_removed_and_reported():
    access = ToolAccessSet(is_admin=False, allowed=frozenset({"internal:excel_export"}))
    uc, repo, resolver = _uc(access)
    res = await uc.execute("src", "forker", None, [], "rid")

    saved = repo.save.call_args.args[0]
    assert [w.tool_id for w in saved.workers] == ["excel_export", ""]  # 서브에이전트는 유지
    assert [w.tool_id for w in res.workers] == ["excel_export", ""]
    assert [(e.tool_id, e.name) for e in res.excluded_tools] == [
        ("internal:python_code_executor", "Python 코드 실행")
    ]
    resolver.for_user_id.assert_awaited_once_with("forker", "rid")


async def test_tool_guidelines_block_rebuilt_without_excluded_tool():
    access = ToolAccessSet(is_admin=False, allowed=frozenset({"internal:excel_export"}))
    uc, repo, _ = _uc(access)
    res = await uc.execute("src", "forker", None, [], "rid")
    saved = repo.save.call_args.args[0]
    assert "python_code_executor" not in saved.system_prompt
    assert "excel_export" in saved.system_prompt
    assert res.system_prompt == saved.system_prompt
    assert saved.system_prompt.startswith("역할 설명")


async def test_all_allowed_keeps_everything_and_prompt():
    uc, repo, _ = _uc(ToolAccessSet.admin())
    res = await uc.execute("src", "forker", None, [], "rid")
    saved = repo.save.call_args.args[0]
    assert len(saved.workers) == 3
    assert saved.system_prompt == PROMPT
    assert res.excluded_tools == []


async def test_without_resolver_behaves_as_before():
    uc, repo, _ = _uc(None)
    res = await uc.execute("src", "forker", None, [], "rid")
    assert len(repo.save.call_args.args[0].workers) == 3
    assert res.excluded_tools == []


async def test_permission_check_happens_before_tool_lookup():
    # 포크 자체가 거부되는 경우 권한 조회를 하지 않는다
    uc, repo, resolver = _uc(ToolAccessSet.admin())
    src = _source()
    src.visibility = "private"
    repo.find_by_id.return_value = src
    with pytest.raises(PermissionError):
        await uc.execute("src", "forker", None, [], "rid")
    resolver.for_user_id.assert_not_awaited()
