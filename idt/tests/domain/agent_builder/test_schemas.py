"""Domain schemas 단위 테스트 — mock 금지."""
from datetime import datetime, timezone

import pytest

from src.domain.agent_builder.schemas import (
    AgentDefinition,
    WorkerDefinition,
    WorkflowDefinition,
    WorkflowSkeleton,
    ToolMeta,
)


def _make_worker(tool_id: str = "tavily_search", sort_order: int = 0) -> WorkerDefinition:
    return WorkerDefinition(
        tool_id=tool_id,
        worker_id=f"{tool_id}_worker",
        description="테스트 워커",
        sort_order=sort_order,
    )


def _make_agent(workers: list[WorkerDefinition] | None = None) -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id="test-agent-id",
        user_id="user-1",
        name="테스트 에이전트",
        description="테스트 요청",
        system_prompt="당신은 테스트 에이전트입니다.",
        flow_hint="search 후 export",
        workers=workers or [_make_worker()],
        model_name="gpt-4o-mini",
        status="active",
        created_at=now,
        updated_at=now,
    )


# ── WorkerDefinition ─────────────────────────────────────────────


class TestWorkerDefinition:
    def test_create_worker_definition(self):
        worker = _make_worker("tavily_search", sort_order=0)
        assert worker.tool_id == "tavily_search"
        assert worker.worker_id == "tavily_search_worker"
        assert worker.sort_order == 0

    def test_worker_default_sort_order_is_zero(self):
        worker = WorkerDefinition(
            tool_id="excel_export",
            worker_id="export_worker",
            description="엑셀 저장",
        )
        assert worker.sort_order == 0


# ── WorkflowSkeleton ─────────────────────────────────────────────


class TestWorkflowSkeleton:
    def test_create_skeleton_with_workers(self):
        workers = [_make_worker("tavily_search", 0), _make_worker("excel_export", 1)]
        skeleton = WorkflowSkeleton(workers=workers, flow_hint="search 후 export")
        assert len(skeleton.workers) == 2
        assert skeleton.flow_hint == "search 후 export"

    def test_skeleton_workers_preserves_order(self):
        workers = [_make_worker("excel_export", 1), _make_worker("tavily_search", 0)]
        skeleton = WorkflowSkeleton(workers=workers, flow_hint="힌트")
        assert skeleton.workers[0].tool_id == "excel_export"
        assert skeleton.workers[1].tool_id == "tavily_search"


# ── AgentDefinition ──────────────────────────────────────────────


class TestAgentDefinition:
    def test_to_workflow_definition_sorts_by_sort_order(self):
        workers = [
            _make_worker("excel_export", sort_order=1),
            _make_worker("tavily_search", sort_order=0),
        ]
        agent = _make_agent(workers=workers)
        wf = agent.to_workflow_definition()
        assert isinstance(wf, WorkflowDefinition)
        assert wf.workers[0].tool_id == "tavily_search"
        assert wf.workers[1].tool_id == "excel_export"

    def test_to_workflow_definition_uses_system_prompt_as_supervisor_prompt(self):
        agent = _make_agent()
        wf = agent.to_workflow_definition()
        assert wf.supervisor_prompt == agent.system_prompt

    def test_to_workflow_definition_preserves_flow_hint(self):
        agent = _make_agent()
        wf = agent.to_workflow_definition()
        assert wf.flow_hint == agent.flow_hint

    def test_apply_update_changes_system_prompt(self):
        agent = _make_agent()
        agent.apply_update(system_prompt="새 프롬프트", name=None)
        assert agent.system_prompt == "새 프롬프트"

    def test_apply_update_changes_name(self):
        agent = _make_agent()
        agent.apply_update(system_prompt=None, name="새 이름")
        assert agent.name == "새 이름"

    def test_apply_update_with_none_does_not_change(self):
        agent = _make_agent()
        original_prompt = agent.system_prompt
        original_name = agent.name
        agent.apply_update(system_prompt=None, name=None)
        assert agent.system_prompt == original_prompt
        assert agent.name == original_name

    def test_apply_update_both_fields(self):
        agent = _make_agent()
        agent.apply_update(system_prompt="새 프롬프트", name="새 이름")
        assert agent.system_prompt == "새 프롬프트"
        assert agent.name == "새 이름"
