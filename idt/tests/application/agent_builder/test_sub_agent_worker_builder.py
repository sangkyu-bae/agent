"""SubAgentWorkerBuilder 단위 테스트 (가시성 기반 접근 검증)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.schemas import SubAgentConfigRequest
from src.application.agent_builder.sub_agent_worker_builder import SubAgentWorkerBuilder
from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition


def _make_agent(
    agent_id: str,
    user_id: str,
    visibility: str = "private",
    department_id: str | None = None,
    status: str = "active",
    name: str = "서브봇",
) -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id=agent_id,
        user_id=user_id,
        name=name,
        description="설명",
        system_prompt="프롬프트",
        flow_hint="test",
        workers=[WorkerDefinition("tavily_search", "w0", "검색", 0)],
        llm_model_id="model-1",
        status=status,
        visibility=visibility,
        department_id=department_id,
        created_at=now,
        updated_at=now,
    )


def _sub_worker(ref_agent_id: str) -> WorkerDefinition:
    return WorkerDefinition(
        tool_id=f"sub_agent_{ref_agent_id[:8]}",
        worker_id=f"sub_{ref_agent_id}",
        description="서브",
        sort_order=1,
        worker_type="sub_agent",
        ref_agent_id=ref_agent_id,
    )


def _make_builder(sub_agent: AgentDefinition | None):
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=sub_agent)
    return SubAgentWorkerBuilder(repository=repo, logger=MagicMock()), repo


def _make_graph_builder(agents_map: dict[str, AgentDefinition]):
    repo = MagicMock()

    async def _find(agent_id, request_id):
        return agents_map.get(agent_id)

    repo.find_by_id = AsyncMock(side_effect=_find)
    return SubAgentWorkerBuilder(repository=repo, logger=MagicMock()), repo


async def _build(builder, ref_id="sub-1", parent_user="user-1", dept_ids=None,
                 parent_agent_id=None):
    return await builder.build(
        configs=[SubAgentConfigRequest(ref_agent_id=ref_id, description="역할")],
        parent_user_id=parent_user,
        parent_department_ids=dept_ids or [],
        existing_tool_count=1,
        request_id="req-1",
        parent_agent_id=parent_agent_id,
    )


class TestSubAgentWorkerBuilder:
    @pytest.mark.asyncio
    async def test_owned_agent_allowed(self):
        builder, _ = _make_builder(_make_agent("sub-1", "user-1"))
        workers = await _build(builder)
        assert len(workers) == 1
        assert workers[0].worker_type == "sub_agent"
        assert workers[0].ref_agent_id == "sub-1"
        assert workers[0].sort_order == 1

    @pytest.mark.asyncio
    async def test_public_other_user_allowed_without_subscription(self):
        builder, _ = _make_builder(_make_agent("sub-1", "other", visibility="public"))
        workers = await _build(builder)
        assert len(workers) == 1

    @pytest.mark.asyncio
    async def test_department_match_allowed(self):
        sub = _make_agent("sub-1", "other", visibility="department", department_id="d1")
        builder, _ = _make_builder(sub)
        workers = await _build(builder, dept_ids=["d1"])
        assert len(workers) == 1

    @pytest.mark.asyncio
    async def test_department_mismatch_denied(self):
        sub = _make_agent("sub-1", "other", visibility="department", department_id="d1")
        builder, _ = _make_builder(sub)
        with pytest.raises(PermissionError):
            await _build(builder, dept_ids=["d2"])

    @pytest.mark.asyncio
    async def test_private_other_user_denied(self):
        builder, _ = _make_builder(_make_agent("sub-1", "other", visibility="private"))
        with pytest.raises(PermissionError):
            await _build(builder)

    @pytest.mark.asyncio
    async def test_not_found_raises(self):
        builder, _ = _make_builder(None)
        with pytest.raises(ValueError, match="찾을 수 없"):
            await _build(builder)

    @pytest.mark.asyncio
    async def test_deleted_raises(self):
        builder, _ = _make_builder(_make_agent("sub-1", "user-1", status="deleted"))
        with pytest.raises(ValueError, match="찾을 수 없"):
            await _build(builder)

    @pytest.mark.asyncio
    async def test_self_reference_denied(self):
        builder, _ = _make_builder(_make_agent("parent", "user-1"))
        with pytest.raises(ValueError, match="자기 자신"):
            await _build(builder, ref_id="parent", parent_agent_id="parent")

    @pytest.mark.asyncio
    async def test_indirect_cycle_denied(self):
        """parent → B, 그런데 B → parent 인 간접 순환은 차단."""
        b = _make_agent("B", "user-1")
        b.workers = b.workers + [_sub_worker("parent")]
        parent = _make_agent("parent", "user-1")
        builder, _ = _make_graph_builder({"B": b, "parent": parent})
        with pytest.raises(ValueError, match="순환"):
            await _build(builder, ref_id="B", parent_agent_id="parent")

    @pytest.mark.asyncio
    async def test_nesting_depth_exceeded_denied(self):
        """parent → A → B → C (깊이 3) 은 최대 깊이 2 초과로 차단."""
        c = _make_agent("C", "user-1")
        b = _make_agent("B", "user-1")
        b.workers = b.workers + [_sub_worker("C")]
        a = _make_agent("A", "user-1")
        a.workers = a.workers + [_sub_worker("B")]
        builder, _ = _make_graph_builder({"A": a, "B": b, "C": c})
        with pytest.raises(ValueError, match="깊이"):
            await _build(builder, ref_id="A", parent_agent_id="parent")
