"""SweepExecutor 검증.

Design Ref: D7 — 모델을 순차 실행한다(병렬 금지: 지연 오염·rate limit).
Design Ref: D12 — 개별 run 실패가 스윕 전체를 죽이지 않는다.
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.eval_sweep.sweep_executor import SweepExecutor
from src.domain.eval_sweep.entity import EvaluationSweep
from src.domain.ragas.value_objects import EvalConfig, MetricType, TestCase


def _sweep(model_ids=("m-1", "m-2", "m-3")):
    return EvaluationSweep(
        id="sw-1",
        name="스윕",
        agent_id="ag-1",
        testset_id="ts-1",
        judge_llm_model_id="m-judge",
        model_ids=list(model_ids),
        metrics=["answer_relevancy"],
        total_runs=len(model_ids),
        created_at=datetime.now(timezone.utc),
    )


def _make(run_now=None):
    batch = MagicMock()
    batch.run_now = run_now or AsyncMock()

    repo = MagicMock()
    repo.update = AsyncMock()

    @asynccontextmanager
    async def _session_factory():
        session = MagicMock()

        @asynccontextmanager
        async def _begin():
            yield None

        session.begin = _begin
        yield session

    executor = SweepExecutor(
        batch_executor=batch,
        sweep_repo_builder=lambda s: repo,
        session_factory=_session_factory,
        logger=MagicMock(),
    )
    return executor, batch, repo


_CONFIG = EvalConfig(metrics=[MetricType.ANSWER_RELEVANCY], agent_id="ag-1")
_CASES = [TestCase(question="q")]


async def _drain(executor, sweep, run_ids):
    executor.kickoff(sweep, run_ids, _CASES, _CONFIG, "u-1", "req-1")
    # kickoff이 만든 백그라운드 태스크가 끝날 때까지 양보한다.
    for _ in range(50):
        await asyncio.sleep(0)
        if sweep.status in ("completed", "failed"):
            return


class TestSequentialExecution:
    @pytest.mark.asyncio
    async def test_runs_every_model_once(self):
        executor, batch, _ = _make()
        sweep = _sweep()

        await _drain(executor, sweep, ["r-1", "r-2", "r-3"])

        assert batch.run_now.await_count == 3

    @pytest.mark.asyncio
    async def test_each_run_gets_its_own_model_override(self):
        """D1 — 모델별로 llm_model_id_override만 바뀐 설정이 내려가야 한다."""
        executor, batch, _ = _make()
        sweep = _sweep()

        await _drain(executor, sweep, ["r-1", "r-2", "r-3"])

        configs = [c.args[3] for c in batch.run_now.await_args_list]
        assert [c.llm_model_id_override for c in configs] == ["m-1", "m-2", "m-3"]
        # 나머지 설정은 공유된다
        assert all(c.agent_id == "ag-1" for c in configs)

    @pytest.mark.asyncio
    async def test_runs_are_not_overlapped(self):
        """병렬이면 지연 측정이 서로 오염된다 — 한 번에 하나만 떠야 한다."""
        in_flight = 0
        peak = 0

        async def _slow(*args, **kwargs):
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0)
            in_flight -= 1

        executor, _, _ = _make(run_now=AsyncMock(side_effect=_slow))
        sweep = _sweep()

        await _drain(executor, sweep, ["r-1", "r-2", "r-3"])

        assert peak == 1

    @pytest.mark.asyncio
    async def test_marks_sweep_completed(self):
        executor, _, _ = _make()
        sweep = _sweep()

        await _drain(executor, sweep, ["r-1", "r-2", "r-3"])

        assert sweep.status == "completed"
        assert sweep.completed_runs == 3
        assert sweep.completed_at is not None

    @pytest.mark.asyncio
    async def test_progress_is_persisted_per_model(self):
        """프론트 폴링이 진행률을 읽으므로 모델마다 반영돼야 한다."""
        executor, _, repo = _make()
        sweep = _sweep()

        await _drain(executor, sweep, ["r-1", "r-2", "r-3"])

        # running 표시 1회 + 모델 3회
        assert repo.update.await_count >= 4


class TestFailureIsolation:
    """D12 / FR-13 — 한 모델의 실패가 스윕 전체를 죽이면 안 된다.

    5개 중 4개만 성공해도 4개 비교는 성립한다. 실패 사실 자체가 그 모델에 대한
    평가 정보이므로, 나머지를 버리는 대신 행 단위로 격리한다.
    """

    @staticmethod
    def _fail_only(target_model_id: str):
        """지정한 모델에서만 예외를 던지는 run_now."""
        async def _run(run_id, target_type, testcases, config, user_id, request_id):
            if config.llm_model_id_override == target_model_id:
                raise RuntimeError(f"{target_model_id} 연결 실패")
        return AsyncMock(side_effect=_run)

    @pytest.mark.asyncio
    async def test_middle_model_failure_does_not_stop_the_rest(self):
        executor, batch, _ = _make(run_now=self._fail_only("m-2"))
        sweep = _sweep()

        await _drain(executor, sweep, ["r-1", "r-2", "r-3"])

        # 실패한 m-2 뒤의 m-3까지 반드시 시도되어야 한다
        attempted = [
            c.args[3].llm_model_id_override for c in batch.run_now.await_args_list
        ]
        assert attempted == ["m-1", "m-2", "m-3"]

    @pytest.mark.asyncio
    async def test_sweep_still_completes_on_partial_failure(self):
        executor, _, _ = _make(run_now=self._fail_only("m-1"))
        sweep = _sweep()

        await _drain(executor, sweep, ["r-1", "r-2", "r-3"])

        assert sweep.status == "completed"
        assert sweep.completed_runs == 3

    @pytest.mark.asyncio
    async def test_first_model_failure_does_not_stop_the_rest(self):
        executor, batch, _ = _make(run_now=self._fail_only("m-1"))
        sweep = _sweep()

        await _drain(executor, sweep, ["r-1", "r-2", "r-3"])

        assert batch.run_now.await_count == 3

    @pytest.mark.asyncio
    async def test_orchestration_failure_marks_sweep_failed(self):
        """개별 run이 아니라 오케스트레이션(상태 저장 등)이 깨진 경우는 스윕 실패다."""
        executor, _, repo = _make()
        repo.update = AsyncMock(side_effect=RuntimeError("저장 폭발"))
        sweep = _sweep(model_ids=("m-1",))

        executor.kickoff(sweep, ["r-1"], _CASES, _CONFIG, "u-1", "req-1")
        for _ in range(50):
            await asyncio.sleep(0)

        assert sweep.status == "failed"
        assert "저장 폭발" in (sweep.error_message or "")
