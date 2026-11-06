"""RunToolTraceService — 기록 조회·조립과 실패 흡수 (agent-run-tool-trace §2.1, §6)."""
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.agent_run.run_tool_trace import RunToolTraceService
from src.domain.agent_run.entities import AgentRunStep, ToolCall
from src.domain.agent_run.tool_trace_policy import ToolTraceKind
from src.domain.agent_run.value_objects import NodeType, RunId, StepStatus
from src.domain.tool_catalog.entity import ToolCatalogEntry

RUN_A = RunId("11111111-1111-1111-1111-111111111111")
RUN_B = RunId("22222222-2222-2222-2222-222222222222")
T0 = datetime(2026, 11, 3, tzinfo=timezone.utc)


def _call(run_id: RunId, id_: str = "t1", tool_name: str = "wiki_read") -> ToolCall:
    return ToolCall(
        id=id_, run_id=run_id, step_id="w", tool_name=tool_name, llm_model_id=None,
        arguments_json={"article_id": "a1"}, result_summary="본문", result_json=None,
        token_usage=None, total_cost_usd=None, latency_ms=5, status="SUCCESS",
        error_text=None, created_at=T0,
    )


def _step(run_id: RunId, id_: str, index: int, node_type: NodeType, output: Optional[str]):
    return AgentRunStep(
        id=id_, run_id=run_id, step_index=index, node_name=id_, node_type=node_type,
        llm_model_id=None, status=StepStatus.SUCCESS, input_summary=None,
        output_summary=output, started_at=T0, ended_at=None, latency_ms=None,
        error_text=None,
    )


def _service(tool_calls=None, steps=None, catalog=None, max_items: int = 50):
    runs = MagicMock()
    runs.find_tool_calls_by_runs = AsyncMock(return_value=tool_calls or {})
    runs.find_steps_by_runs = AsyncMock(return_value=steps or {})
    tools = MagicMock()
    tools.list_active = AsyncMock(return_value=catalog or [])
    logger = MagicMock()
    return RunToolTraceService(runs, tools, logger, max_items=max_items), runs, tools, logger


@pytest.mark.asyncio
class TestBuildForRuns:
    async def test_no_runs_issue_no_query(self) -> None:
        service, runs, tools, _ = _service()
        assert await service.build_for_runs([], "req") == {}
        runs.find_tool_calls_by_runs.assert_not_awaited()
        tools.list_active.assert_not_awaited()

    async def test_runs_without_tool_calls_skip_step_and_catalog_queries(self) -> None:
        service, runs, tools, _ = _service()
        assert await service.build_for_runs([RUN_A], "req") == {}
        runs.find_steps_by_runs.assert_not_awaited()
        tools.list_active.assert_not_awaited()

    async def test_groups_traces_by_run_with_fixed_query_count(self) -> None:
        service, runs, tools, _ = _service(
            tool_calls={RUN_A.value: [_call(RUN_A)], RUN_B.value: [_call(RUN_B, "t2")]},
            steps={
                RUN_A.value: [_step(RUN_A, "s", 1, NodeType.SUPERVISOR, "위키를 읽는다"),
                              _step(RUN_A, "w", 2, NodeType.WORKER, None)],
                RUN_B.value: [_step(RUN_B, "w", 1, NodeType.WORKER, None)],
            },
            catalog=[ToolCatalogEntry(id="e", tool_id="internal:wiki_read", source="internal",
                                      name="에이전트 위키 열람", description="")],
        )
        built = await service.build_for_runs([RUN_A, RUN_B], "req")
        assert [i.kind for i in built[RUN_A.value].items] == [
            ToolTraceKind.REASONING, ToolTraceKind.TOOL,
        ]
        assert built[RUN_B.value].items[0].label == "에이전트 위키 열람"
        assert runs.find_tool_calls_by_runs.await_count == 1
        assert runs.find_steps_by_runs.await_count == 1
        assert tools.list_active.await_count == 1

    async def test_max_items_is_applied(self) -> None:
        calls = [_call(RUN_A, f"t{i}") for i in range(4)]
        service, *_ = _service(tool_calls={RUN_A.value: calls}, max_items=2)
        trace = (await service.build_for_runs([RUN_A], "req"))[RUN_A.value]
        assert (len(trace.items), trace.omitted_count) == (2, 2)

    async def test_tool_call_read_failure_returns_empty(self) -> None:
        service, runs, _, logger = _service()
        error = RuntimeError("db")
        runs.find_tool_calls_by_runs.side_effect = error
        assert await service.build_for_runs([RUN_A], "req") == {}
        assert logger.warning.call_args.kwargs["exception"] is error

    async def test_step_read_failure_returns_empty(self) -> None:
        service, runs, _, logger = _service(tool_calls={RUN_A.value: [_call(RUN_A)]})
        error = RuntimeError("db")
        runs.find_steps_by_runs.side_effect = error
        assert await service.build_for_runs([RUN_A], "req") == {}
        assert logger.warning.call_args.kwargs["exception"] is error

    async def test_catalog_failure_keeps_trace_with_fallback_labels(self) -> None:
        service, _, tools, _ = _service(tool_calls={RUN_A.value: [_call(RUN_A)]})
        tools.list_active.side_effect = RuntimeError("db")
        trace = (await service.build_for_runs([RUN_A], "req"))[RUN_A.value]
        assert trace.items[0].label == "wiki_read"

    async def test_policy_failure_drops_only_that_run(self) -> None:
        service, _, _, logger = _service(
            tool_calls={RUN_A.value: [_call(RUN_A)], RUN_B.value: [_call(RUN_B, "t2")]},
        )
        from src.domain.agent_run.tool_trace_policy import ToolTracePolicy
        original = ToolTracePolicy.build
        error = ValueError("boom")

        def flaky(evidence, *, max_items):
            if evidence.tool_calls[0].run_id == RUN_A:
                raise error
            return original(evidence, max_items=max_items)

        with patch.object(ToolTracePolicy, "build", side_effect=flaky):
            built = await service.build_for_runs([RUN_A, RUN_B], "req")
        assert list(built) == [RUN_B.value]
        assert logger.warning.call_args.kwargs["exception"] is error
