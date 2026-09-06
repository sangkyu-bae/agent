"""AgentDefinition.replace_tool_workers — agent-update-tool-editing D §3.1.

replace_sub_agents(도구 보존·서브에이전트 교체)의 대칭 연산:
서브에이전트를 보존하고 도구 워커만 교체하며 sort_order를 재정렬한다.
"""
from datetime import datetime, timezone

from src.domain.agent_builder.schemas import AgentDefinition, WorkerDefinition


def _tool(tool_id: str, sort_order: int = 0) -> WorkerDefinition:
    return WorkerDefinition(
        tool_id=tool_id,
        worker_id=f"{tool_id}_worker",
        description=f"desc-{tool_id}",
        sort_order=sort_order,
    )


def _sub(ref_agent_id: str, sort_order: int = 0) -> WorkerDefinition:
    return WorkerDefinition(
        tool_id="",
        worker_id=f"sub_{ref_agent_id}",
        description="서브에이전트",
        sort_order=sort_order,
        worker_type="sub_agent",
        ref_agent_id=ref_agent_id,
    )


def _agent(workers: list[WorkerDefinition]) -> AgentDefinition:
    now = datetime.now(timezone.utc)
    return AgentDefinition(
        id="agent-1",
        user_id="user-1",
        name="테스트 에이전트",
        description="설명",
        system_prompt="지침",
        flow_hint="",
        workers=workers,
        llm_model_id="model-1",
        status="active",
        created_at=now,
        updated_at=now,
    )


def test_replaces_tool_workers_and_preserves_sub_agents():
    agent = _agent([_tool("a", 0), _tool("b", 1), _sub("child-1", 2)])

    agent.replace_tool_workers([_tool("c"), _tool("d"), _tool("e")])

    assert [w.tool_id for w in agent.workers if w.worker_type == "tool"] == [
        "c", "d", "e",
    ]
    subs = [w for w in agent.workers if w.worker_type == "sub_agent"]
    assert [w.ref_agent_id for w in subs] == ["child-1"]


def test_reorders_sort_order_tools_first_then_sub_agents():
    agent = _agent([_tool("a", 0), _sub("child-1", 1), _sub("child-2", 2)])

    agent.replace_tool_workers([_tool("x", 99), _tool("y", 99)])

    assert [(w.worker_id, w.sort_order) for w in agent.workers] == [
        ("x_worker", 0),
        ("y_worker", 1),
        ("sub_child-1", 2),
        ("sub_child-2", 3),
    ]


def test_empty_tool_workers_keeps_only_sub_agents():
    agent = _agent([_tool("a", 0), _sub("child-1", 1)])

    agent.replace_tool_workers([])

    assert len(agent.workers) == 1
    assert agent.workers[0].worker_type == "sub_agent"
    assert agent.workers[0].sort_order == 0


def test_is_symmetric_with_replace_sub_agents():
    """도구만 있는 에이전트에 두 연산을 연달아 적용해도 서로를 지우지 않는다."""
    agent = _agent([_tool("a", 0)])

    agent.replace_sub_agents([_sub("child-1")])
    agent.replace_tool_workers([_tool("b"), _tool("c")])

    assert [w.worker_id for w in agent.workers] == [
        "b_worker", "c_worker", "sub_child-1",
    ]
    assert [w.sort_order for w in agent.workers] == [0, 1, 2]
