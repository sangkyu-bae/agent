"""GetAgentUseCase.tool_access 테스트 (tool-access-control FR-13, Design §0 F6)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from src.application.agent_builder.get_agent_use_case import GetAgentUseCase
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition
from src.domain.tool_access.value_objects import ToolAccessSet

SRV = "7f3c0000-0000-0000-0000-000000000001"


def _agent() -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id="a1", user_id="1", name="n", description="d", system_prompt="p", flow_hint="h",
        workers=[
            WorkerDefinition(tool_id="excel_export", worker_id="w1", description=""),
            WorkerDefinition(tool_id=f"mcp:{SRV}:write_ticket", worker_id="w2", description=""),
            WorkerDefinition(tool_id="", worker_id="w3", description="", worker_type="sub_agent",
                             ref_agent_id="child"),
        ],
        llm_model_id="m", status="active", created_at=now, updated_at=now,
    )


def _uc(resolver):
    repo = MagicMock()
    agent = _agent()
    child = _agent()
    child.name = "자식"

    async def find(agent_id, rid):
        return agent if agent_id == "a1" else child

    repo.find_by_id = AsyncMock(side_effect=find)
    dept = MagicMock()
    dept.find_by_id = AsyncMock(return_value=None)
    return GetAgentUseCase(
        repository=repo, dept_repository=dept, logger=MagicMock(), tool_access_resolver=resolver,
    )


def _resolver(access=None, error=None):
    r = MagicMock()
    r.for_user_id = AsyncMock(return_value=access, side_effect=error)
    return r


async def test_tool_access_per_tool_worker():
    access = ToolAccessSet(is_admin=False, allowed=frozenset({"internal:excel_export"}))
    res = await _uc(_resolver(access)).execute("a1", "rid", viewer_user_id="2")
    assert [(t.tool_id, t.name, t.permitted) for t in res.tool_access] == [
        ("internal:excel_export", "Excel 파일 생성", True),
        (f"mcp:{SRV}:write_ticket", "write_ticket", False),
    ]


async def test_no_resolver_or_viewer_is_none():
    assert (await _uc(None).execute("a1", "rid", viewer_user_id="2")).tool_access is None
    res = await _uc(_resolver(ToolAccessSet.admin())).execute("a1", "rid")
    assert res.tool_access is None


async def test_lookup_failure_degrades_to_none():
    res = await _uc(_resolver(error=RuntimeError("db"))).execute("a1", "rid", viewer_user_id="2")
    assert res is not None
    assert res.tool_access is None
