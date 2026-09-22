"""BackgroundJobWorker 단위 테스트 — Mock 의존성, tick 단위 검증 (Design §6)."""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.background_job.worker import BackgroundJobWorker
from src.domain.background_job.entity import BackgroundJob

_NOW = datetime(2026, 8, 11, 3, 0)


class _FakeCM:
    def __init__(self, value=None):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *args):
        return False


def _job(job_id="j1", session_id=None) -> BackgroundJob:
    return BackgroundJob(
        id=job_id,
        user_id="u1",
        agent_id="a1",
        source="chat",
        query="시장 조사해줘",
        session_id=session_id,
        run_id=None,
        status="running",  # claim 이후 상태
        error_message=None,
        seen_at=None,
        queued_at=_NOW,
        started_at=_NOW,
        finished_at=None,
        request_id="req-0",
        created_at=_NOW,
        updated_at=_NOW,
    )


def _make_worker(
    claimed=None,
    run_uc=None,
    assemble=None,
    trigger_uc=None,
    dispatcher=None,
    max_concurrency=2,
    schedule_tick_interval=0.0,
    enabled=True,
    now_fn=None,
):
    session = AsyncMock()
    session.begin = MagicMock(return_value=_FakeCM())
    session_factory = MagicMock(return_value=_FakeCM(session))

    job_repo = MagicMock()
    job_repo.claim_queued = AsyncMock(return_value=claimed or [])
    job_repo.finish = AsyncMock(return_value=True)
    job_repo.reconcile_orphan_running = AsyncMock(return_value=2)

    if run_uc is None:
        run_uc = MagicMock()
        run_uc.execute = AsyncMock(
            return_value=MagicMock(session_id="sess-1", run_id="run-1")
        )
    if assemble is None:
        assemble = AsyncMock(return_value=MagicMock(department_ids=["d1"]))

    worker = BackgroundJobWorker(
        session_factory=session_factory,
        job_repo_builder=MagicMock(return_value=job_repo),
        run_agent_uc_builder=MagicMock(return_value=run_uc),
        assemble_auth_context=assemble,
        logger=MagicMock(),
        schedule_trigger_uc=trigger_uc,
        outbound_dispatcher=dispatcher,
        poll_interval_sec=0.01,
        schedule_tick_interval_sec=schedule_tick_interval,
        max_concurrency=max_concurrency,
        enabled=enabled,
        now_fn=now_fn or (lambda: _NOW),
    )
    return worker, job_repo, run_uc, assemble


class TestExecuteJob:
    @pytest.mark.asyncio
    async def test_success_records_session_and_run_id(self):
        worker, job_repo, run_uc, _ = _make_worker(claimed=[_job()])
        await worker.tick_once()
        await worker.drain()
        run_uc.execute.assert_awaited_once()
        args, kwargs = job_repo.finish.call_args
        assert args[0] == "j1" and args[1] == "success"
        assert kwargs["session_id"] == "sess-1"
        assert kwargs["run_id"] == "run-1"

    @pytest.mark.asyncio
    async def test_run_request_carries_job_fields(self):
        worker, _, run_uc, _ = _make_worker(
            claimed=[_job(session_id="sess-9")]
        )
        await worker.tick_once()
        await worker.drain()
        request = run_uc.execute.call_args[0][1]
        assert request.query == "시장 조사해줘"
        assert request.user_id == "u1"
        assert request.session_id == "sess-9"
        kwargs = run_uc.execute.call_args.kwargs
        assert kwargs["viewer_user_id"] == "u1"
        assert kwargs["viewer_department_ids"] == ["d1"]

    @pytest.mark.asyncio
    async def test_failure_marks_failed_and_survives(self):
        run_uc = MagicMock()
        run_uc.execute = AsyncMock(side_effect=RuntimeError("LLM 폭발"))
        worker, job_repo, _, _ = _make_worker(claimed=[_job()], run_uc=run_uc)
        await worker.tick_once()
        await worker.drain()
        args, kwargs = job_repo.finish.call_args
        assert args[1] == "failed"
        assert "LLM 폭발" in kwargs["error_message"]

    @pytest.mark.asyncio
    async def test_missing_user_marks_failed_without_run(self):
        assemble = AsyncMock(return_value=None)
        worker, job_repo, run_uc, _ = _make_worker(
            claimed=[_job()], assemble=assemble
        )
        await worker.tick_once()
        await worker.drain()
        run_uc.execute.assert_not_awaited()
        assert job_repo.finish.call_args[0][1] == "failed"


class TestOutbound:
    @pytest.mark.asyncio
    async def test_dispatches_with_job_source(self):
        dispatcher = MagicMock()
        dispatcher.dispatch = AsyncMock()
        worker, _, _, _ = _make_worker(claimed=[_job()], dispatcher=dispatcher)
        await worker.tick_once()
        await worker.drain()
        dispatcher.dispatch.assert_awaited_once()
        args = dispatcher.dispatch.call_args[0]
        assert args[0] == "a1"
        assert args[2] == "job"

    @pytest.mark.asyncio
    async def test_failed_job_also_dispatches_outbound(self):
        """Plan FR-06 — 실패도 발송 대상. answer=None 이 실패 신호."""
        dispatcher = MagicMock()
        dispatcher.dispatch = AsyncMock()
        run_uc = MagicMock()
        run_uc.execute = AsyncMock(side_effect=RuntimeError("LLM 폭발"))
        worker, job_repo, _, _ = _make_worker(
            claimed=[_job(session_id="sess-9")],
            run_uc=run_uc,
            dispatcher=dispatcher,
        )
        await worker.tick_once()
        await worker.drain()
        assert job_repo.finish.call_args[0][1] == "failed"
        dispatcher.dispatch.assert_awaited_once()
        args = dispatcher.dispatch.call_args[0]
        assert args[0] == "a1"
        assert args[1].answer is None
        assert args[1].session_id == "sess-9"
        assert args[2] == "job"

    @pytest.mark.asyncio
    async def test_dispatch_failure_does_not_affect_job(self):
        dispatcher = MagicMock()
        dispatcher.dispatch = AsyncMock(side_effect=RuntimeError("발송 실패"))
        worker, job_repo, _, _ = _make_worker(
            claimed=[_job()], dispatcher=dispatcher
        )
        await worker.tick_once()
        await worker.drain()
        assert job_repo.finish.call_args[0][1] == "success"  # D12 불영향


class TestConcurrency:
    @pytest.mark.asyncio
    async def test_no_claim_when_slots_full(self):
        gate = asyncio.Event()

        async def _blocked(*args, **kwargs):
            await gate.wait()
            return MagicMock(session_id="sess-1", run_id="run-1")

        run_uc = MagicMock()
        run_uc.execute = AsyncMock(side_effect=_blocked)
        worker, job_repo, _, _ = _make_worker(
            claimed=[_job()], run_uc=run_uc, max_concurrency=1
        )
        await worker.tick_once()  # 슬롯 1 소진
        await asyncio.sleep(0)
        await worker.tick_once()  # 슬롯 0 → claim 미호출
        assert job_repo.claim_queued.await_count == 1
        assert job_repo.claim_queued.call_args[0][0] == 1  # limit = 빈 슬롯
        gate.set()
        await worker.drain()

    def test_invalid_concurrency_rejected(self):
        with pytest.raises(ValueError):
            _make_worker(max_concurrency=0)


class TestScheduleTick:
    @pytest.mark.asyncio
    async def test_delegates_to_trigger_use_case(self):
        trigger = MagicMock()
        trigger.execute = AsyncMock()
        worker, _, _, _ = _make_worker(trigger_uc=trigger)
        await worker.tick_once()
        await asyncio.sleep(0)
        trigger.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_interval_gate_skips_early_tick(self):
        trigger = MagicMock()
        trigger.execute = AsyncMock()
        clock = {"now": _NOW}
        worker, _, _, _ = _make_worker(
            trigger_uc=trigger,
            schedule_tick_interval=30.0,
            now_fn=lambda: clock["now"],
        )
        await worker.tick_once()
        await asyncio.sleep(0)
        clock["now"] = _NOW + timedelta(seconds=10)  # 30s 미경과
        await worker.tick_once()
        await asyncio.sleep(0)
        assert trigger.execute.await_count == 1
        clock["now"] = _NOW + timedelta(seconds=31)
        await worker.tick_once()
        await asyncio.sleep(0)
        assert trigger.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_single_flight_skips_while_previous_running(self):
        gate = asyncio.Event()

        async def _blocked(*args, **kwargs):
            await gate.wait()

        trigger = MagicMock()
        trigger.execute = AsyncMock(side_effect=_blocked)
        worker, _, _, _ = _make_worker(trigger_uc=trigger)
        await worker.tick_once()
        await asyncio.sleep(0)
        await worker.tick_once()  # 직전 틱 미완 → skip
        assert trigger.execute.await_count == 1
        gate.set()
        await asyncio.sleep(0)

    @pytest.mark.asyncio
    async def test_trigger_failure_does_not_kill_tick(self):
        trigger = MagicMock()
        trigger.execute = AsyncMock(side_effect=RuntimeError("tick 실패"))
        worker, job_repo, _, _ = _make_worker(trigger_uc=trigger)
        await worker.tick_once()
        await asyncio.sleep(0)
        job_repo.claim_queued.assert_awaited()  # job 처리는 계속


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_reconcile_delegates(self):
        worker, job_repo, _, _ = _make_worker()
        count = await worker.reconcile()
        assert count == 2
        job_repo.reconcile_orphan_running.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disabled_worker_does_not_start(self):
        worker, _, _, _ = _make_worker(enabled=False)
        worker.start()
        assert worker.status()["running"] is False

    @pytest.mark.asyncio
    async def test_stop_marks_inflight_job_failed(self):
        async def _forever(*args, **kwargs):
            await asyncio.Event().wait()

        run_uc = MagicMock()
        run_uc.execute = AsyncMock(side_effect=_forever)
        worker, job_repo, _, _ = _make_worker(claimed=[_job()], run_uc=run_uc)
        await worker.tick_once()
        await asyncio.sleep(0)
        await worker.stop()
        args, kwargs = job_repo.finish.call_args
        assert args[1] == "failed"
        assert "서버 종료" in kwargs["error_message"]

    @pytest.mark.asyncio
    async def test_tick_exception_recorded_and_swallowed(self):
        worker, job_repo, _, _ = _make_worker()
        job_repo.claim_queued = AsyncMock(side_effect=RuntimeError("DB down"))
        await worker.tick_once()  # 예외 미전파 (루프 생존)
        assert worker.status()["last_error"] is not None


class TestApprovalTick:
    """approval-gate Check G5 — 예약 집행을 주기적으로 부르는 주체.

    이전에는 /internal/approvals/tick 을 외부 cron 이 치지 않으면 scheduled
    건이 영원히 집행되지 않았다. 스케줄 tick 과 같은 워커 루프에 합류시킨다.
    """

    @staticmethod
    def _worker_with_approval(interval=0.0, runner=None):
        worker, *_ = _make_worker()
        if runner is None:
            runner = MagicMock()
            runner.run = AsyncMock(return_value=MagicMock(executed_count=1))
        worker._approval_tick_runner = runner
        worker._approval_tick_interval = interval
        return worker, runner

    @pytest.mark.asyncio
    async def test_tick_마다_승인_집행을_돌린다(self):
        worker, runner = self._worker_with_approval()
        await worker.tick_once()
        await asyncio.sleep(0)  # 생성된 태스크 1회 진행
        await worker._approval_task
        runner.run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_주기_미만이면_건너뛴다(self):
        worker, runner = self._worker_with_approval(interval=3600.0)
        await worker.tick_once()
        await worker._approval_task
        await worker.tick_once()  # 같은 시각 — 주기 미경과
        assert runner.run.await_count == 1

    @pytest.mark.asyncio
    async def test_직전_tick_미완이면_중복_실행하지_않는다(self):
        """single-flight — 집행이 길어져도 겹쳐 돌면 이중 집행 위험."""
        gate = asyncio.Event()
        runner = MagicMock()

        async def _slow(request_id):
            await gate.wait()

        runner.run = _slow
        worker, _ = self._worker_with_approval(runner=runner)
        await worker.tick_once()
        first = worker._approval_task
        await worker.tick_once()
        assert worker._approval_task is first
        gate.set()
        await first

    @pytest.mark.asyncio
    async def test_러너_미주입이면_아무것도_하지_않는다(self):
        """무회귀 — 기존 배선에서는 승인 tick 이 없다."""
        worker, *_ = _make_worker()
        await worker.tick_once()
        assert getattr(worker, "_approval_task", None) is None

    @pytest.mark.asyncio
    async def test_러너_예외가_워커를_죽이지_않는다(self):
        runner = MagicMock()
        runner.run = AsyncMock(side_effect=RuntimeError("DB 장애"))
        worker, _ = self._worker_with_approval(runner=runner)
        await worker.tick_once()
        await worker._approval_task  # 예외가 태스크 밖으로 새지 않는다
