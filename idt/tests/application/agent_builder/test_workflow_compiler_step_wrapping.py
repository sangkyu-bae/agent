"""WorkflowCompiler M3 step wrapping 검증.

AGENT-OBS-003 Design §8.2 — 6 cases.
각 노드 타입(supervisor/worker/quality_gate/answer/search/sub_agent)이
track_step 컨텍스트로 감싸져 ai_run_step row를 생성하는지 검증.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from src.application.agent_builder.supervisor_hooks import DefaultHooks
from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.application.agent_run.tracker import RunTracker
from src.domain.agent_builder.schemas import (
    SupervisorConfig,
    WorkerDefinition,
    WorkflowDefinition,
)
from src.domain.agent_run.value_objects import NodeType, RunId, StepStatus
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel
from src.infrastructure.llm.usage_callback import UsageCallback


RUN_ID = "11111111-1111-1111-1111-111111111111"


def _make_llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-1",
        provider="openai",
        model_name="gpt-4o-mini",
        display_name="gpt-4o-mini",
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=128000,
        is_active=True,
        is_default=True,
        created_at=now,
        updated_at=now,
    )


def _make_compiler() -> tuple[WorkflowCompiler, MagicMock]:
    mock_tool = MagicMock()
    tool_factory = MagicMock()
    tool_factory.create = MagicMock(return_value=mock_tool)
    llm_factory = MagicMock(spec=LLMFactoryInterface)
    llm_factory.create.return_value = MagicMock()
    logger = MagicMock()
    compiler = WorkflowCompiler(
        tool_factory=tool_factory,
        llm_factory=llm_factory,
        logger=logger,
        hooks=DefaultHooks(),
    )
    return compiler, tool_factory


def _make_tracker_and_callback() -> tuple[MagicMock, UsageCallback]:
    tracker = MagicMock(spec=RunTracker)
    # record_step가 호출될 때마다 고유 step_id 반환
    tracker.record_step = AsyncMock(side_effect=lambda **kw: f"step-{kw['step_index']}")
    tracker.update_step = AsyncMock(return_value=None)
    callback = UsageCallback(
        tracker=tracker,
        run_id=RunId(RUN_ID),
        user_id="user-1",
        agent_id="agent-1",
        logger=MagicMock(),
    )
    return tracker, callback


def _workflow_with_workers(*worker_ids: str) -> WorkflowDefinition:
    return WorkflowDefinition(
        supervisor_prompt="test",
        workers=[
            WorkerDefinition(
                tool_id=f"tool_{i}",
                worker_id=wid,
                description=f"worker {wid}",
                sort_order=i,
            )
            for i, wid in enumerate(worker_ids)
        ],
        flow_hint="test",
    )


class TestNoWrappingWhenTrackerNone:
    @pytest.mark.asyncio
    async def test_no_record_step_when_tracker_none(self) -> None:
        """tracker=None → 원본 노드 fn 그대로 (관측성 비활성)."""
        compiler, _ = _make_compiler()
        workflow = _workflow_with_workers("w1")
        tracker, callback = _make_tracker_and_callback()

        with patch(
            "src.application.agent_builder.workflow_compiler.create_react_agent",
            return_value=AsyncMock(return_value={"messages": []}),
        ):
            # tracker=None이면 callback/run_id 있어도 wrapping 안 함
            graph = await compiler.compile(
                workflow, _make_llm_model(), "req-1",
                tracker=None, callback=callback, run_id=RunId(RUN_ID),
            )

        assert graph is not None
        tracker.record_step.assert_not_called()


class TestSupervisorWrapping:
    @pytest.mark.asyncio
    async def test_supervisor_node_calls_record_step_with_supervisor_type(self) -> None:
        compiler, _ = _make_compiler()
        workflow = _workflow_with_workers("w1")
        tracker, callback = _make_tracker_and_callback()

        # supervisor LLM이 FINISH를 즉시 반환하도록 mock
        sup_llm = MagicMock()
        decision_mock = MagicMock()
        decision_mock.next = "__end__"
        decision_mock.answer = "직접 답변"
        sup_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=decision_mock
        )
        # workflow_compiler가 llm_factory.create()로 받는 llm
        compiler._llm_factory.create.return_value = sup_llm  # type: ignore

        with patch(
            "src.application.agent_builder.workflow_compiler.create_react_agent",
            return_value=AsyncMock(return_value={"messages": []}),
        ):
            graph = await compiler.compile(
                workflow, _make_llm_model(), "req-1",
                tracker=tracker, callback=callback, run_id=RunId(RUN_ID),
            )
            await graph.ainvoke({
                "messages": [{"role": "user", "content": "hi"}],
                "iteration_count": 0,
                "max_iterations": 10,
                "token_usage": 0,
                "token_limit": 1000000,
                "available_workers": ["w1"],
                "skipped_workers": [],
                "retry_counts": {},
                "max_retries_per_worker": 2,
                "quality_gate_enabled": False,
                "last_worker_id": "",
                "next_worker": "",
                "forced_worker": "",
                "quality_gate_result": "",
            })

        # supervisor가 record_step 호출 → node_type=SUPERVISOR
        calls = [c.kwargs for c in tracker.record_step.await_args_list]
        sup_calls = [c for c in calls if c["node_name"] == "supervisor"]
        assert len(sup_calls) >= 1
        assert sup_calls[0]["node_type"] == NodeType.SUPERVISOR


class TestWorkerAndQualityGateWrapping:
    @pytest.mark.asyncio
    async def test_worker_wrapped_with_worker_type(self) -> None:
        """react worker가 _wrap_step(WORKER, ...)로 감싸지는지."""
        compiler, _ = _make_compiler()
        workflow = _workflow_with_workers("w1")
        tracker, callback = _make_tracker_and_callback()

        # supervisor → w1 → quality_gate(disabled) → __end__
        sup_llm = MagicMock()
        decision_1 = MagicMock(next="w1", answer=None)
        decision_2 = MagicMock(next="__end__", answer=None)
        sup_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            side_effect=[decision_1, decision_2]
        )
        # final-answer-node: 워커 실행 후 __end__ → final_answer가 llm.ainvoke 호출
        sup_llm.ainvoke = AsyncMock(return_value=AIMessage(content="최종 답변"))
        compiler._llm_factory.create.return_value = sup_llm  # type: ignore

        worker_agent_mock = MagicMock()
        worker_agent_mock.ainvoke = AsyncMock(return_value={"messages": []})
        with patch(
            "src.application.agent_builder.workflow_compiler.create_react_agent",
            return_value=worker_agent_mock,
        ):
            graph = await compiler.compile(
                workflow, _make_llm_model(), "req-1",
                tracker=tracker, callback=callback, run_id=RunId(RUN_ID),
            )
            await graph.ainvoke({
                "messages": [{"role": "user", "content": "hi"}],
                "iteration_count": 0,
                "max_iterations": 10,
                "token_usage": 0,
                "token_limit": 1000000,
                "available_workers": ["w1"],
                "skipped_workers": [],
                "retry_counts": {},
                "max_retries_per_worker": 2,
                "quality_gate_enabled": False,
                "last_worker_id": "",
                "next_worker": "",
                "forced_worker": "",
                "quality_gate_result": "",
            })

        calls = [c.kwargs for c in tracker.record_step.await_args_list]
        worker_calls = [c for c in calls if c["node_name"] == "w1"]
        assert len(worker_calls) >= 1
        assert worker_calls[0]["node_type"] == NodeType.WORKER
        # final_answer step도 기록됨 (NodeType.OTHER)
        final_calls = [c for c in calls if c["node_name"] == "final_answer"]
        assert len(final_calls) == 1
        assert final_calls[0]["node_type"] == NodeType.OTHER

    @pytest.mark.asyncio
    async def test_quality_gate_wrapped_with_gate_type(self) -> None:
        compiler, _ = _make_compiler()
        workflow = _workflow_with_workers("w1")
        tracker, callback = _make_tracker_and_callback()

        sup_llm = MagicMock()
        decision_1 = MagicMock(next="w1", answer=None)
        decision_2 = MagicMock(next="__end__", answer=None)
        sup_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            side_effect=[decision_1, decision_2]
        )
        sup_llm.ainvoke = AsyncMock(return_value=AIMessage(content="최종 답변"))
        compiler._llm_factory.create.return_value = sup_llm  # type: ignore

        worker_agent_mock = MagicMock()
        worker_agent_mock.ainvoke = AsyncMock(return_value={"messages": []})
        with patch(
            "src.application.agent_builder.workflow_compiler.create_react_agent",
            return_value=worker_agent_mock,
        ):
            graph = await compiler.compile(
                workflow, _make_llm_model(), "req-1",
                tracker=tracker, callback=callback, run_id=RunId(RUN_ID),
            )
            await graph.ainvoke({
                "messages": [{"role": "user", "content": "hi"}],
                "iteration_count": 0,
                "max_iterations": 10,
                "token_usage": 0,
                "token_limit": 1000000,
                "available_workers": ["w1"],
                "skipped_workers": [],
                "retry_counts": {},
                "max_retries_per_worker": 2,
                "quality_gate_enabled": True,  # ★ 활성화
                "last_worker_id": "",
                "next_worker": "",
                "forced_worker": "",
                "quality_gate_result": "",
            })

        calls = [c.kwargs for c in tracker.record_step.await_args_list]
        gate_calls = [c for c in calls if c["node_name"] == "quality_gate"]
        assert len(gate_calls) >= 1
        assert gate_calls[0]["node_type"] == NodeType.GATE


class TestStepIndexMonotonic:
    @pytest.mark.asyncio
    async def test_step_index_increments_sequentially(self) -> None:
        """한 run의 노드 4개 → step_index 1,2,3,4."""
        compiler, _ = _make_compiler()
        workflow = _workflow_with_workers("w1")
        tracker, callback = _make_tracker_and_callback()

        sup_llm = MagicMock()
        d1 = MagicMock(next="w1", answer=None)
        d2 = MagicMock(next="__end__", answer=None)
        sup_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            side_effect=[d1, d2]
        )
        sup_llm.ainvoke = AsyncMock(return_value=AIMessage(content="최종 답변"))
        compiler._llm_factory.create.return_value = sup_llm  # type: ignore

        worker_agent_mock = MagicMock()
        worker_agent_mock.ainvoke = AsyncMock(return_value={"messages": []})
        with patch(
            "src.application.agent_builder.workflow_compiler.create_react_agent",
            return_value=worker_agent_mock,
        ):
            graph = await compiler.compile(
                workflow, _make_llm_model(), "req-1",
                tracker=tracker, callback=callback, run_id=RunId(RUN_ID),
            )
            await graph.ainvoke({
                "messages": [{"role": "user", "content": "hi"}],
                "iteration_count": 0,
                "max_iterations": 10,
                "token_usage": 0,
                "token_limit": 1000000,
                "available_workers": ["w1"],
                "skipped_workers": [],
                "retry_counts": {},
                "max_retries_per_worker": 2,
                "quality_gate_enabled": False,
                "last_worker_id": "",
                "next_worker": "",
                "forced_worker": "",
                "quality_gate_result": "",
            })

        indices = sorted(c.kwargs["step_index"] for c in tracker.record_step.await_args_list)
        # 최소 3 step (supervisor, w1, supervisor 재호출) — 모두 unique + sequential
        assert indices == list(range(1, len(indices) + 1)), \
            f"step_index가 1부터 단조 증가해야 함, got {indices}"

    @pytest.mark.asyncio
    async def test_update_step_called_with_success_after_each_node(self) -> None:
        compiler, _ = _make_compiler()
        workflow = _workflow_with_workers("w1")
        tracker, callback = _make_tracker_and_callback()

        sup_llm = MagicMock()
        sup_llm.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=MagicMock(next="__end__", answer="done")
        )
        compiler._llm_factory.create.return_value = sup_llm  # type: ignore

        with patch(
            "src.application.agent_builder.workflow_compiler.create_react_agent",
            return_value=AsyncMock(return_value={"messages": []}),
        ):
            graph = await compiler.compile(
                workflow, _make_llm_model(), "req-1",
                tracker=tracker, callback=callback, run_id=RunId(RUN_ID),
            )
            await graph.ainvoke({
                "messages": [{"role": "user", "content": "hi"}],
                "iteration_count": 0,
                "max_iterations": 10,
                "token_usage": 0,
                "token_limit": 1000000,
                "available_workers": ["w1"],
                "skipped_workers": [],
                "retry_counts": {},
                "max_retries_per_worker": 2,
                "quality_gate_enabled": False,
                "last_worker_id": "",
                "next_worker": "",
                "forced_worker": "",
                "quality_gate_result": "",
            })

        update_calls = tracker.update_step.await_args_list
        assert len(update_calls) >= 1
        for c in update_calls:
            assert c.kwargs["status"] == StepStatus.SUCCESS
