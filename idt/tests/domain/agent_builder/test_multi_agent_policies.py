"""멀티 에이전트 조합 관련 도메인 정책 단위 테스트 — mock 금지."""
import pytest

from src.domain.agent_builder.policies import (
    AgentBuilderPolicy,
    CircularReferenceError,
    CircularReferencePolicy,
    NestingDepthExceededError,
    NestingDepthPolicy,
    SubAgentAccessPolicy,
)
from src.domain.agent_builder.schemas import WorkerDefinition


# ── WorkerDefinition sub_agent 타입 ────────────────────────────


class TestWorkerDefinitionSubAgent:
    def test_default_worker_type_is_tool(self):
        w = WorkerDefinition(
            tool_id="tavily_search",
            worker_id="tavily_worker",
            description="웹 검색",
        )
        assert w.worker_type == "tool"
        assert w.ref_agent_id is None

    def test_sub_agent_type_with_ref_id(self):
        w = WorkerDefinition(
            tool_id="",
            worker_id="sub_agent_analyzer",
            description="분석 에이전트",
            worker_type="sub_agent",
            ref_agent_id="agent-uuid-1",
        )
        assert w.worker_type == "sub_agent"
        assert w.ref_agent_id == "agent-uuid-1"

    def test_sub_agent_without_ref_id_raises(self):
        with pytest.raises(ValueError, match="ref_agent_id"):
            WorkerDefinition(
                tool_id="",
                worker_id="sub_agent_x",
                description="에이전트",
                worker_type="sub_agent",
                ref_agent_id=None,
            )

    def test_invalid_worker_type_raises(self):
        with pytest.raises(ValueError, match="worker_type"):
            WorkerDefinition(
                tool_id="tavily_search",
                worker_id="w",
                description="d",
                worker_type="invalid",
            )

    def test_tool_type_without_tool_id_raises(self):
        with pytest.raises(ValueError, match="tool_id"):
            WorkerDefinition(
                tool_id="",
                worker_id="w",
                description="d",
                worker_type="tool",
            )


# ── CircularReferencePolicy ────────────────────────────────────


class TestCircularReferencePolicy:
    def test_no_cycle_passes(self):
        visited = {"agent-a", "agent-b"}
        CircularReferencePolicy.validate_no_cycle("agent-c", visited)

    def test_detects_direct_cycle(self):
        visited = {"agent-a"}
        with pytest.raises(CircularReferenceError, match="순환참조"):
            CircularReferencePolicy.validate_no_cycle("agent-a", visited)

    def test_detects_indirect_cycle(self):
        visited = {"agent-a", "agent-b", "agent-c"}
        with pytest.raises(CircularReferenceError):
            CircularReferencePolicy.validate_no_cycle("agent-a", visited)

    def test_error_includes_cycle_path(self):
        visited = {"agent-a", "agent-b"}
        with pytest.raises(CircularReferenceError) as exc_info:
            CircularReferencePolicy.validate_no_cycle("agent-a", visited)
        assert "agent-a" in str(exc_info.value)

    def test_empty_visited_always_passes(self):
        CircularReferencePolicy.validate_no_cycle("agent-x", set())


# ── NestingDepthPolicy ─────────────────────────────────────────


class TestNestingDepthPolicy:
    def test_depth_zero_passes(self):
        NestingDepthPolicy.validate_depth(0)

    def test_depth_one_passes(self):
        NestingDepthPolicy.validate_depth(1)

    def test_depth_at_max_passes(self):
        NestingDepthPolicy.validate_depth(NestingDepthPolicy.MAX_NESTING_DEPTH)

    def test_depth_over_max_raises(self):
        over = NestingDepthPolicy.MAX_NESTING_DEPTH + 1
        with pytest.raises(NestingDepthExceededError, match="중첩 깊이"):
            NestingDepthPolicy.validate_depth(over)

    def test_max_nesting_depth_is_two(self):
        assert NestingDepthPolicy.MAX_NESTING_DEPTH == 2


# ── SubAgentAccessPolicy ──────────────────────────────────────


class TestSubAgentAccessPolicy:
    def test_owner_can_use(self):
        assert SubAgentAccessPolicy.can_use_as_sub_agent(
            parent_owner_id="user-1",
            sub_agent_owner_id="user-1",
            is_subscribed=False,
        ) is True

    def test_subscribed_can_use(self):
        assert SubAgentAccessPolicy.can_use_as_sub_agent(
            parent_owner_id="user-1",
            sub_agent_owner_id="user-2",
            is_subscribed=True,
        ) is True

    def test_non_owner_non_subscribed_denied(self):
        assert SubAgentAccessPolicy.can_use_as_sub_agent(
            parent_owner_id="user-1",
            sub_agent_owner_id="user-2",
            is_subscribed=False,
        ) is False


# ── AgentBuilderPolicy.validate_worker_count (혼합) ───────────


def _tool_worker(tool_id: str = "tavily_search", idx: int = 0) -> WorkerDefinition:
    return WorkerDefinition(
        tool_id=tool_id,
        worker_id=f"{tool_id}_worker_{idx}",
        description="도구",
        sort_order=idx,
        worker_type="tool",
    )


def _sub_agent_worker(ref_id: str = "agent-1", idx: int = 0) -> WorkerDefinition:
    return WorkerDefinition(
        tool_id=f"sub_agent_{ref_id[:8]}",
        worker_id=f"sub_agent_{idx}",
        description="서브 에이전트",
        sort_order=idx,
        worker_type="sub_agent",
        ref_agent_id=ref_id,
    )


class TestValidateWorkerCount:
    def test_single_tool_passes(self):
        AgentBuilderPolicy.validate_worker_count([_tool_worker()])

    def test_single_sub_agent_passes(self):
        AgentBuilderPolicy.validate_worker_count([_sub_agent_worker()])

    def test_mixed_workers_passes(self):
        workers = [
            _tool_worker("tavily_search", 0),
            _tool_worker("excel_export", 1),
            _sub_agent_worker("agent-1", 2),
        ]
        AgentBuilderPolicy.validate_worker_count(workers)

    def test_empty_workers_passes(self):
        # agent-instruction-required: 워커 0개(순수 대화형) 허용 (하한 제거)
        AgentBuilderPolicy.validate_worker_count([])

    def test_exceeds_total_max_raises(self):
        workers = [_tool_worker(f"tool_{i}", i) for i in range(7)]
        with pytest.raises(ValueError, match="최대"):
            AgentBuilderPolicy.validate_worker_count(workers)

    def test_exceeds_sub_agent_max_raises(self):
        workers = [_sub_agent_worker(f"agent-{i}", i) for i in range(4)]
        with pytest.raises(ValueError, match="서브 에이전트"):
            AgentBuilderPolicy.validate_worker_count(workers)

    def test_exceeds_tool_max_raises(self):
        workers = [_tool_worker(f"tool_{i}", i) for i in range(6)]
        with pytest.raises(ValueError, match="최대"):
            AgentBuilderPolicy.validate_worker_count(workers)
