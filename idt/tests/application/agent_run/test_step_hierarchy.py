"""track_step 계층(parent_step_id·depth)·latency 기록 테스트.

Design Ref: subagent-step-observability §3.3~3.5 (H1~H4, L1~L2) / §8.2 B1~B11
Plan SC: SC-1, SC-2, SC-4

서브에이전트 래퍼 노드 안에서 자식 그래프 노드가 실행되는 상황을 track_step
중첩으로 재현한다. 부모 판별은 기록 시점의 callback._current_step_id,
깊이는 RunContext.step_depth 로 전파된다.
"""
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.agent_run.context import (
    RunContext,
    get_current_run_context,
    reset_run_context,
    set_current_run_context,
    with_step_id,
)
from src.application.agent_run.step_tracking import track_step
from src.application.agent_run.tracker import RunTracker
from src.domain.agent_run.value_objects import NodeType, RunId, StepStatus
from src.infrastructure.llm.usage_callback import UsageCallback

RUN = RunId("11111111-1111-1111-1111-111111111111")
_MODULE = "src.application.agent_run.step_tracking"


def _tracker(*step_ids: Any) -> MagicMock:
    tracker = MagicMock(spec=RunTracker)
    tracker.record_step = AsyncMock(side_effect=list(step_ids))
    tracker.update_step = AsyncMock(return_value=None)
    return tracker


def _callback(tracker: MagicMock) -> UsageCallback:
    return UsageCallback(tracker=tracker, run_id=RUN, user_id="u", agent_id="a",
                         logger=MagicMock())


@contextmanager
def _run_ctx(cb: UsageCallback) -> Iterator[None]:
    token = set_current_run_context(
        RunContext(run_id=RUN, user_id="u", agent_id="a", callback=cb)
    )
    try:
        yield
    finally:
        reset_run_context(token)


def _step(tracker, cb, name: str):
    return track_step(tracker=tracker, callback=cb, run_id=RUN, node_name=name,
                      node_type=NodeType.WORKER, logger=MagicMock())


def _recorded(tracker: MagicMock) -> list[tuple[str, Any, int]]:
    """record_step 호출 순서대로 (node_name, parent_step_id, depth)."""
    return [
        (c.kwargs["node_name"], c.kwargs["parent_step_id"], c.kwargs["depth"])
        for c in tracker.record_step.await_args_list
    ]


class TestHierarchy:
    @pytest.mark.asyncio
    async def test_B1_최상위_노드는_부모_없음_깊이_0(self):
        tracker = _tracker("s-1")
        cb = _callback(tracker)
        with _run_ctx(cb):
            async with _step(tracker, cb, "supervisor"):
                pass
        assert _recorded(tracker) == [("supervisor", None, 0)]

    @pytest.mark.asyncio
    async def test_B2_B4_B5_래퍼_안_자식과_형제_그리고_다음_최상위(self):
        tracker = _tracker("w-1", "c-1", "c-2", "s-2")
        cb = _callback(tracker)
        with _run_ctx(cb):
            async with _step(tracker, cb, "sub_agent_x_0"):
                async with _step(tracker, cb, "supervisor"):
                    pass
                async with _step(tracker, cb, "quality_gate"):
                    pass
            async with _step(tracker, cb, "supervisor"):
                pass
        assert _recorded(tracker) == [
            ("sub_agent_x_0", None, 0),
            ("supervisor", "w-1", 1),
            ("quality_gate", "w-1", 1),
            ("supervisor", None, 0),
        ]

    @pytest.mark.asyncio
    async def test_B3_손자_그래프는_깊이_2(self):
        tracker = _tracker("w-1", "w-2", "c-1")
        cb = _callback(tracker)
        with _run_ctx(cb):
            async with _step(tracker, cb, "sub_a"):
                async with _step(tracker, cb, "sub_b"):
                    async with _step(tracker, cb, "worker"):
                        pass
        assert _recorded(tracker) == [
            ("sub_a", None, 0), ("sub_b", "w-1", 1), ("worker", "w-2", 2),
        ]

    @pytest.mark.asyncio
    async def test_B6_자식_예외_뒤에도_복원된다(self):
        tracker = _tracker("w-1", "c-1", "c-2", "s-2")
        cb = _callback(tracker)
        with _run_ctx(cb):
            async with _step(tracker, cb, "sub_agent_x_0"):
                with pytest.raises(RuntimeError):
                    async with _step(tracker, cb, "boom"):
                        raise RuntimeError("x")
                async with _step(tracker, cb, "after"):
                    pass
            async with _step(tracker, cb, "top"):
                pass
            # 예외 경로를 거친 뒤에도 컨텍스트 깊이가 최상위로 복원된다
            assert get_current_run_context().step_depth == 0
            assert cb._current_step_id is None
        assert _recorded(tracker)[2:] == [("after", "w-1", 1), ("top", None, 0)]

    @pytest.mark.asyncio
    async def test_B7_컨텍스트가_없으면_깊이_1로_폴백(self):
        tracker = _tracker("w-1", "c-1")
        cb = _callback(tracker)
        async with _step(tracker, cb, "sub_agent_x_0"):
            async with _step(tracker, cb, "child"):
                pass
        assert _recorded(tracker) == [("sub_agent_x_0", None, 0), ("child", "w-1", 1)]

    @pytest.mark.asyncio
    async def test_G3_컨텍스트가_다른_step을_가리키면_깊이_1로_폴백(self):
        """H4 — ctx는 있으나 ctx.step_id 가 부모와 다르면 깊이를 추정하지 않는다."""
        tracker = _tracker("c-1")
        cb = _callback(tracker)
        cb._current_step_id = "w-9"  # 부모는 있으나 컨텍스트와 불일치
        token = set_current_run_context(
            RunContext(run_id=RUN, user_id="u", agent_id="a", callback=cb,
                       step_id="other", step_depth=3)
        )
        try:
            async with _step(tracker, cb, "child"):
                pass
        finally:
            reset_run_context(token)
        assert _recorded(tracker) == [("child", "w-9", 1)]

    @pytest.mark.asyncio
    async def test_B10_래퍼_기록_실패면_자식은_최상위로(self):
        tracker = _tracker(None, "c-1")
        cb = _callback(tracker)
        with _run_ctx(cb):
            async with _step(tracker, cb, "sub_agent_x_0"):
                async with _step(tracker, cb, "child"):
                    pass
        assert _recorded(tracker)[1] == ("child", None, 0)


class TestLatency:
    @pytest.mark.asyncio
    async def test_B8_latency는_monotonic_차로_전달(self):
        tracker = _tracker("s-1")
        cb = _callback(tracker)
        fake_time = SimpleNamespace(monotonic=MagicMock(side_effect=[100.0, 100.0505]))
        with patch(f"{_MODULE}.time", fake_time):
            async with _step(tracker, cb, "quality_gate"):
                pass
        assert tracker.update_step.await_args.kwargs["latency_ms"] == 50

    @pytest.mark.asyncio
    async def test_B8_예외_경로도_latency_전달(self):
        tracker = _tracker("s-1")
        cb = _callback(tracker)
        fake_time = SimpleNamespace(monotonic=MagicMock(side_effect=[5.0, 5.2]))
        with patch(f"{_MODULE}.time", fake_time):
            with pytest.raises(ValueError):
                async with _step(tracker, cb, "worker"):
                    raise ValueError("x")
        kwargs = tracker.update_step.await_args.kwargs
        assert kwargs["status"] == StepStatus.FAILED
        assert kwargs["latency_ms"] == 200

    @pytest.mark.asyncio
    async def test_latency는_음수가_되지_않는다(self):
        tracker = _tracker("s-1")
        cb = _callback(tracker)
        fake_time = SimpleNamespace(monotonic=MagicMock(side_effect=[10.0, 9.9]))
        with patch(f"{_MODULE}.time", fake_time):
            async with _step(tracker, cb, "x"):
                pass
        assert tracker.update_step.await_args.kwargs["latency_ms"] == 0


class TestContextHelper:
    def test_B11_with_step_id는_기본적으로_깊이를_유지(self):
        cb = MagicMock()
        ctx = RunContext(run_id=RUN, user_id="u", agent_id="a", callback=cb, step_depth=2)
        assert with_step_id(ctx, "s-9").step_depth == 2
        assert with_step_id(ctx, "s-9", step_depth=3).step_depth == 3
        assert RunContext(run_id=RUN, user_id="u", agent_id="a", callback=cb).step_depth == 0


class TestTrackerPersistence:
    """B9·B12 연계 — RunTracker 가 계층·latency 를 저장소로 넘긴다."""

    @staticmethod
    def _tracker_with_repo(repo: MagicMock) -> tuple[RunTracker, Any]:
        class _Tx:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return None

        class _Session(_Tx):
            def begin(self):
                return _Tx()

        tracker = RunTracker(session_factory=lambda: _Session(),
                             cost_calculator=MagicMock(), model_name_resolver=MagicMock(),
                             logger=MagicMock())
        return tracker, patch("src.application.agent_run.tracker.SqlAlchemyAgentRunRepository",
                              return_value=repo)

    @pytest.mark.asyncio
    async def test_record_step이_계층을_엔티티에_싣는다(self):
        repo = MagicMock()
        repo.save_step = AsyncMock()
        tracker, repo_patch = self._tracker_with_repo(repo)
        with repo_patch:
            await tracker.record_step(
                run_id=RUN, step_index=3, node_name="supervisor",
                node_type=NodeType.SUPERVISOR, llm_model_id=None,
                status=StepStatus.STARTED, parent_step_id="w-1", depth=1,
            )
        saved = repo.save_step.await_args.args[0]
        assert (saved.parent_step_id, saved.depth) == ("w-1", 1)

    @pytest.mark.asyncio
    async def test_B9_update_step은_전달된_latency를_우선한다(self):
        from datetime import datetime, timezone

        from src.domain.agent_run.entities import AgentRunStep

        step = AgentRunStep(
            id="s-1", run_id=RUN, step_index=1, node_name="x", node_type=NodeType.GATE,
            llm_model_id=None, status=StepStatus.STARTED, input_summary=None,
            output_summary=None, started_at=datetime.now(timezone.utc), ended_at=None,
            latency_ms=None, error_text=None,
        )
        repo = MagicMock()
        repo.find_steps = AsyncMock(return_value=[step])
        repo.update_step = AsyncMock()
        tracker, repo_patch = self._tracker_with_repo(repo)
        with repo_patch:
            await tracker.update_step(step_id="s-1", run_id=RUN,
                                      status=StepStatus.SUCCESS, latency_ms=42)
        assert repo.update_step.await_args.args[0].latency_ms == 42

    @pytest.mark.asyncio
    async def test_B9_latency_미전달이면_기존_계산(self):
        from datetime import datetime, timedelta, timezone

        from src.domain.agent_run.entities import AgentRunStep

        step = AgentRunStep(
            id="s-1", run_id=RUN, step_index=1, node_name="x", node_type=NodeType.GATE,
            llm_model_id=None, status=StepStatus.STARTED, input_summary=None,
            output_summary=None,
            started_at=datetime.now(timezone.utc) - timedelta(seconds=2),
            ended_at=None, latency_ms=None, error_text=None,
        )
        repo = MagicMock()
        repo.find_steps = AsyncMock(return_value=[step])
        repo.update_step = AsyncMock()
        tracker, repo_patch = self._tracker_with_repo(repo)
        with repo_patch:
            await tracker.update_step(step_id="s-1", run_id=RUN, status=StepStatus.SUCCESS)
        assert repo.update_step.await_args.args[0].latency_ms >= 1900
