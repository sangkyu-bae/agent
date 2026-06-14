"""track_step async context manager 단위 테스트.

AGENT-OBS-003 (M3) Design §8.2 — ~10 cases.
"""
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage

from src.application.agent_run.context import (
    RunContext,
    get_current_run_context,
    reset_run_context,
    set_current_run_context,
)
from src.application.agent_run.step_tracking import (
    _StepContext,
    _summarize_state_input,
    _summarize_state_output,
    track_step,
)
from src.application.agent_run.tracker import RunTracker
from src.domain.agent_run.value_objects import NodeType, RunId, StepStatus
from src.infrastructure.llm.usage_callback import UsageCallback


RUN_ID_VALUE = "11111111-1111-1111-1111-111111111111"


def _make_tracker_mock(record_step_return: Any = "step-001") -> MagicMock:
    tracker = MagicMock(spec=RunTracker)
    tracker.record_step = AsyncMock(return_value=record_step_return)
    tracker.update_step = AsyncMock(return_value=None)
    return tracker


def _make_callback(tracker: MagicMock) -> UsageCallback:
    return UsageCallback(
        tracker=tracker,
        run_id=RunId(RUN_ID_VALUE),
        user_id="user-1",
        agent_id="agent-1",
        logger=MagicMock(),
    )


@pytest.fixture
def run_id() -> RunId:
    return RunId(RUN_ID_VALUE)


@pytest.fixture
def logger() -> MagicMock:
    return MagicMock()


class TestTrackStepEnterPhase:
    @pytest.mark.asyncio
    async def test_records_started_with_step_index_1(
        self, run_id: RunId, logger: MagicMock
    ) -> None:
        tracker = _make_tracker_mock("step-001")
        cb = _make_callback(tracker)

        async with track_step(
            tracker=tracker,
            callback=cb,
            run_id=run_id,
            node_name="supervisor",
            node_type=NodeType.SUPERVISOR,
            input_summary="user=hi",
            logger=logger,
        ):
            pass

        args = tracker.record_step.await_args.kwargs
        assert args["step_index"] == 1
        assert args["status"] == StepStatus.STARTED
        assert args["node_type"] == NodeType.SUPERVISOR
        assert args["node_name"] == "supervisor"
        assert args["input_summary"] == "user=hi"

    @pytest.mark.asyncio
    async def test_sets_current_step_id_and_increments_step_index(
        self, run_id: RunId, logger: MagicMock
    ) -> None:
        tracker = _make_tracker_mock("step-001")
        cb = _make_callback(tracker)

        async with track_step(
            tracker=tracker, callback=cb, run_id=run_id,
            node_name="supervisor", node_type=NodeType.SUPERVISOR,
            logger=logger,
        ):
            assert cb._current_step_id == "step-001"
            assert cb._step_index == 1

        # exit 후 _current_step_id는 복원 (None)
        assert cb._current_step_id is None
        # _step_index는 monotonic 유지
        assert cb._step_index == 1

    @pytest.mark.asyncio
    async def test_updates_run_context_step_id(
        self, run_id: RunId, logger: MagicMock
    ) -> None:
        tracker = _make_tracker_mock("step-001")
        cb = _make_callback(tracker)
        token = set_current_run_context(
            RunContext(run_id=run_id, user_id="u", agent_id="a", callback=cb)
        )
        try:
            async with track_step(
                tracker=tracker, callback=cb, run_id=run_id,
                node_name="supervisor", node_type=NodeType.SUPERVISOR,
                logger=logger,
            ):
                ctx = get_current_run_context()
                assert ctx is not None
                assert ctx.step_id == "step-001"
            ctx_after = get_current_run_context()
            assert ctx_after is not None
            assert ctx_after.step_id is None  # 복원
        finally:
            reset_run_context(token)

    @pytest.mark.asyncio
    async def test_truncates_input_summary_at_1024(
        self, run_id: RunId, logger: MagicMock
    ) -> None:
        tracker = _make_tracker_mock("step-001")
        cb = _make_callback(tracker)
        big = "x" * 5000

        async with track_step(
            tracker=tracker, callback=cb, run_id=run_id,
            node_name="n", node_type=NodeType.WORKER,
            input_summary=big, logger=logger,
        ):
            pass

        args = tracker.record_step.await_args.kwargs
        assert len(args["input_summary"]) <= 1024


class TestTrackStepExitPhase:
    @pytest.mark.asyncio
    async def test_records_success_on_normal_exit_with_output_summary(
        self, run_id: RunId, logger: MagicMock
    ) -> None:
        tracker = _make_tracker_mock("step-001")
        cb = _make_callback(tracker)

        async with track_step(
            tracker=tracker, callback=cb, run_id=run_id,
            node_name="supervisor", node_type=NodeType.SUPERVISOR,
            logger=logger,
        ) as step:
            step.output_summary = "supervisor chose worker_finance"

        upd = tracker.update_step.await_args.kwargs
        assert upd["status"] == StepStatus.SUCCESS
        assert upd["step_id"] == "step-001"
        assert "worker_finance" in upd["output_summary"]
        assert upd["error_text"] is None

    @pytest.mark.asyncio
    async def test_records_failed_on_exception_and_reraises(
        self, run_id: RunId, logger: MagicMock
    ) -> None:
        tracker = _make_tracker_mock("step-001")
        cb = _make_callback(tracker)

        with pytest.raises(RuntimeError, match="node failed"):
            async with track_step(
                tracker=tracker, callback=cb, run_id=run_id,
                node_name="worker", node_type=NodeType.WORKER,
                logger=logger,
            ):
                raise RuntimeError("node failed")

        upd = tracker.update_step.await_args.kwargs
        assert upd["status"] == StepStatus.FAILED
        assert "node failed" in upd["error_text"]
        # 컨텍스트 복원도 정상
        assert cb._current_step_id is None

    @pytest.mark.asyncio
    async def test_truncates_error_text_at_1024(
        self, run_id: RunId, logger: MagicMock
    ) -> None:
        tracker = _make_tracker_mock("step-001")
        cb = _make_callback(tracker)
        big_msg = "e" * 5000

        with pytest.raises(RuntimeError):
            async with track_step(
                tracker=tracker, callback=cb, run_id=run_id,
                node_name="n", node_type=NodeType.WORKER,
                logger=logger,
            ):
                raise RuntimeError(big_msg)

        upd = tracker.update_step.await_args.kwargs
        assert len(upd["error_text"]) <= 1024


class TestTrackStepBestEffort:
    @pytest.mark.asyncio
    async def test_record_step_returns_none_degrades_gracefully(
        self, run_id: RunId, logger: MagicMock
    ) -> None:
        """record_step이 None을 반환하면 enter_step skip, update_step skip."""
        tracker = _make_tracker_mock(record_step_return=None)
        cb = _make_callback(tracker)

        async with track_step(
            tracker=tracker, callback=cb, run_id=run_id,
            node_name="n", node_type=NodeType.WORKER,
            logger=logger,
        ) as step:
            assert step.step_id is None
            # _current_step_id 미오염
            assert cb._current_step_id is None
            # _step_index도 증가 안 함 (enter_step 호출 안 됨)
            assert cb._step_index == 0

        # update_step도 호출되지 않음
        tracker.update_step.assert_not_called()

    @pytest.mark.asyncio
    async def test_record_step_raises_degrades_gracefully(
        self, run_id: RunId, logger: MagicMock
    ) -> None:
        tracker = _make_tracker_mock()
        tracker.record_step.side_effect = RuntimeError("db down")
        cb = _make_callback(tracker)

        async with track_step(
            tracker=tracker, callback=cb, run_id=run_id,
            node_name="n", node_type=NodeType.WORKER,
            logger=logger,
        ):
            assert cb._current_step_id is None
        # update_step skip
        tracker.update_step.assert_not_called()
        logger.warning.assert_called()


class TestTrackStepIsolation:
    @pytest.mark.asyncio
    async def test_step_index_isolated_per_callback_instance(
        self, run_id: RunId, logger: MagicMock
    ) -> None:
        tracker1 = _make_tracker_mock("step-a")
        tracker2 = _make_tracker_mock("step-b")
        cb1 = _make_callback(tracker1)
        cb2 = _make_callback(tracker2)

        async with track_step(
            tracker=tracker1, callback=cb1, run_id=run_id,
            node_name="x", node_type=NodeType.WORKER, logger=logger,
        ):
            async with track_step(
                tracker=tracker2, callback=cb2, run_id=run_id,
                node_name="y", node_type=NodeType.WORKER, logger=logger,
            ):
                assert cb1._step_index == 1
                assert cb2._step_index == 1


class TestSummarizers:
    def test_summarize_state_input_with_user_message(self) -> None:
        state = {
            "messages": [{"role": "user", "content": "안녕하세요"}],
            "iteration_count": 2,
            "last_worker_id": "worker_finance",
        }
        out = _summarize_state_input(state)
        assert out is not None
        assert "iter=2" in out
        assert "worker_finance" in out
        assert "안녕하세요" in out

    def test_summarize_state_input_empty_messages_safe(self) -> None:
        out = _summarize_state_input({})
        assert out is not None
        assert "no user message" in out

    def test_summarize_state_input_invalid_state_returns_safely(self) -> None:
        # Mapping 아닌 입력 — 예외 swallow 후 None
        out = _summarize_state_input("not a dict")  # type: ignore[arg-type]
        # str.get 부재로 예외 → except 분기 → None
        assert out is None

    def test_summarize_state_output_extracts_last_ai_message(self) -> None:
        result = {"messages": [AIMessage(content="final answer")]}
        out = _summarize_state_output(result)
        assert out is not None
        assert "final answer" in out

    def test_summarize_state_output_truncates_at_1024(self) -> None:
        big = AIMessage(content="x" * 5000)
        result = {"messages": [big]}
        out = _summarize_state_output(result)
        assert out is not None
        assert len(out) <= 1024

    def test_summarize_state_output_routing_keys_fallback(self) -> None:
        result = {"next_worker": "worker_finance", "quality_gate_result": "passed"}
        out = _summarize_state_output(result)
        assert out is not None
        assert "worker_finance" in out
        assert "passed" in out

    def test_summarize_state_output_non_dict_returns_str(self) -> None:
        out = _summarize_state_output("plain string")
        assert out == "plain string"

    def test_summarize_state_output_none_returns_none(self) -> None:
        # 빈 dict (메시지/라우팅 키 모두 없음)
        out = _summarize_state_output({})
        assert out is None
