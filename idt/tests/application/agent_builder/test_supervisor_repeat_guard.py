"""수퍼바이저 같은 워커 연속 호출 상한 (claude-agent-e2e-fixes Design §5.4, S1~S5).

2026-11-19 실 E2E: 분석 워커 결과의 수치가 매번 달라 수퍼바이저가 "수치 불일치"로
분석만 4회 재호출(LLM 분석 13회)했다. 연속 상한에서 안내 → 그래도 고르면 종료.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.application.agent_builder.supervisor_hooks import DefaultHooks
from src.application.agent_builder.supervisor_nodes import (
    build_initial_state,
    create_supervisor_node,
)
from src.domain.agent_builder.schemas import WorkerDefinition

_REPEAT_HEADER = "[반복 호출 주의]"


def _state(**overrides) -> dict:
    base = {
        "messages": [{"role": "user", "content": "분석해서 엑셀로"}],
        "iteration_count": 0, "max_iterations": 10,
        "token_usage": 0, "token_limit": 50000,
        "next_worker": "", "last_worker_id": "",
        "available_workers": ["analysis", "excel"],
        "quality_gate_enabled": False, "retry_counts": {}, "max_retries_per_worker": 2,
        "forced_worker": "", "skipped_workers": [], "quality_gate_result": "",
        "attachments": [], "viz_decision": "",
    }
    base.update(overrides)
    return base


def _workers() -> list[WorkerDefinition]:
    return [
        WorkerDefinition(tool_id="data_analysis", worker_id="analysis", description="데이터 분석"),
        WorkerDefinition(tool_id="excel_export", worker_id="excel", description="엑셀 생성"),
    ]


def _llm(next_: str):
    llm = MagicMock()
    decision = MagicMock(next=next_, answer="", reasoning="분석을 다시 해야 한다", task="t")
    llm.with_structured_output.return_value.ainvoke = AsyncMock(return_value=decision)
    return llm


def _node(llm, limit: int, logger=None, hooks=None):
    return create_supervisor_node(
        llm=llm, workers=_workers(), supervisor_prompt="지침",
        hooks=hooks or DefaultHooks(), logger=logger or MagicMock(),
        max_consecutive_worker_calls=limit,
    )


def _prompt(llm) -> str:
    messages = llm.with_structured_output.return_value.ainvoke.call_args.args[0]
    return messages[0]["content"]


@pytest.mark.asyncio
async def test_disabled_limit_keeps_routing_and_prompt():  # S1
    llm = _llm("analysis")
    out = await _node(llm, 0)(_state(repeat_worker_id="analysis", repeat_worker_count=5))
    assert out["next_worker"] == "analysis"
    assert _REPEAT_HEADER not in _prompt(llm)


@pytest.mark.asyncio
async def test_repeat_block_after_limit():  # S2
    llm = _llm("excel")
    await _node(llm, 2)(_state(last_worker_id="analysis",
                               repeat_worker_id="analysis", repeat_worker_count=2))
    prompt = _prompt(llm)
    assert _REPEAT_HEADER in prompt
    assert "analysis" in prompt and "2회" in prompt


@pytest.mark.asyncio
async def test_same_worker_after_limit_ends_run():  # S3
    logger = MagicMock()
    llm = _llm("analysis")
    out = await _node(llm, 2, logger)(_state(last_worker_id="analysis",
                                             repeat_worker_id="analysis", repeat_worker_count=2))
    assert out["next_worker"] == "__end__"
    assert out["_step_output_summary"].startswith("[반복 상한]")
    assert out["repeat_worker_id"] == "" and out["repeat_worker_count"] == 0
    assert "worker repeat limit reached" in [c.args[0] for c in logger.warning.call_args_list]


@pytest.mark.asyncio
async def test_other_worker_resets_counter():  # S4
    out = await _node(_llm("excel"), 2)(_state(last_worker_id="analysis",
                                                repeat_worker_id="analysis", repeat_worker_count=2))
    assert out["next_worker"] == "excel"
    assert (out["repeat_worker_id"], out["repeat_worker_count"]) == ("excel", 1)


@pytest.mark.asyncio
async def test_same_worker_below_limit_increments():
    out = await _node(_llm("analysis"), 2)(_state(last_worker_id="analysis",
                                                   repeat_worker_id="analysis", repeat_worker_count=1))
    assert out["next_worker"] == "analysis"
    assert (out["repeat_worker_id"], out["repeat_worker_count"]) == ("analysis", 2)


@pytest.mark.asyncio
async def test_error_block_has_priority_over_repeat():  # S5
    llm = _llm("excel")
    await _node(llm, 2)(_state(last_worker_id="analysis", last_worker_error="timeout",
                               repeat_worker_id="analysis", repeat_worker_count=2))
    prompt = _prompt(llm)
    assert "[직전 수집 실패]" in prompt
    assert _REPEAT_HEADER not in prompt


@pytest.mark.asyncio
async def test_forced_route_updates_counter():
    hooks = MagicMock()
    hooks.force_worker.return_value = "analysis"
    out = await _node(_llm("excel"), 2, hooks=hooks)(_state(repeat_worker_id="analysis",
                                                           repeat_worker_count=1))
    assert out["next_worker"] == "analysis"
    assert (out["repeat_worker_id"], out["repeat_worker_count"]) == ("analysis", 2)


def test_initial_state_has_repeat_keys():
    config = MagicMock(max_iterations=10, token_limit=50000,
                       quality_gate_enabled=False, max_retries_per_worker=2)
    state = build_initial_state([], config, ["analysis"])
    assert state["repeat_worker_id"] == "" and state["repeat_worker_count"] == 0
