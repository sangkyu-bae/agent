"""BatchEvalExecutor — 백그라운드 배치 평가 실행 (eval-hub Design §2.4)."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.ragas.batch_executor import BatchEvalExecutor
from src.domain.ragas.entities import EvaluationRun
from src.domain.ragas.value_objects import EvalConfig, MetricType, TestCase


def _run(status="pending"):
    return EvaluationRun(
        id="run-1", eval_type="batch", target_type="rag", status=status,
        total_cases=2, created_at=datetime.now(timezone.utc), user_id="7",
    )


def _config(metrics=(MetricType.FAITHFULNESS,)):
    return EvalConfig(metrics=list(metrics), collection_name="col-1")


def _store(run=None):
    store = MagicMock()
    store.get_run = AsyncMock(return_value=run)
    store.update_run = AsyncMock()
    store.save_results_bulk = AsyncMock()
    return store


def _target(answer="답", contexts=("c1",), extra=None):
    target = MagicMock()
    target.execute = AsyncMock(return_value=(answer, list(contexts), extra or {}))
    return target


def _evaluator(scores=None):
    ev = MagicMock()
    ev.evaluate = AsyncMock(return_value=scores or {"faithfulness": 0.9})
    return ev


def _executor(store, evaluator=None, target=None):
    return BatchEvalExecutor(
        store=store,
        evaluator=evaluator or _evaluator(),
        target_executor=target or _target(),
        logger=MagicMock(),
        run_fetch_retries=2,
        retry_delay=0.0,
    )


CASES = [TestCase(question="q1", ground_truth="a1"), TestCase(question="q2")]


async def _run_and_wait(executor, **kwargs):
    executor.kickoff(
        run_id="run-1", target_type="rag", testcases=CASES,
        config=_config(), user_id="7", request_id="rid", **kwargs,
    )
    for _ in range(200):
        if not executor._tasks:
            break
        await asyncio.sleep(0.01)


class TestBatchExecutor:
    @pytest.mark.asyncio
    async def test_정상_완료_결과저장_및_completed(self):
        store = _store(_run())
        executor = _executor(store)

        await _run_and_wait(executor)

        saved = store.save_results_bulk.await_args.args[0]
        assert len(saved) == 2
        assert saved[0].answer == "답"
        assert saved[0].metrics == {"faithfulness": 0.9}
        final = store.update_run.await_args.args[0]
        assert final.status == "completed"

    @pytest.mark.asyncio
    async def test_대상실행_실패시_failed_및_error_message(self):
        store = _store(_run())
        target = MagicMock()
        target.execute = AsyncMock(side_effect=RuntimeError("컬렉션 없음"))
        executor = _executor(store, target=target)

        await _run_and_wait(executor)

        final = store.update_run.await_args.args[0]
        assert final.status == "failed"
        assert "컬렉션 없음" in final.error_message

    @pytest.mark.asyncio
    async def test_run_미가시_재시도후_포기(self):
        store = _store(run=None)
        executor = _executor(store)

        await _run_and_wait(executor)

        assert store.get_run.await_count == 2
        store.save_results_bulk.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_extra_scores가_메트릭에_병합(self):
        store = _store(_run())
        target = _target(extra={"hit_rate": 1.0})
        executor = _executor(store, target=target)

        await _run_and_wait(executor)

        saved = store.save_results_bulk.await_args.args[0]
        assert saved[0].metrics["hit_rate"] == 1.0
        assert saved[0].metrics["faithfulness"] == 0.9
