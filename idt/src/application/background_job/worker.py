"""BackgroundJobWorker: DB 큐 폴링 워커 루프 + 스케줄러 틱 (Design §4-3, D1~D8).

- lifespan 싱글턴 — AsyncSession 을 보유하지 않는다 (session_factory 만, DB-001).
- 루프 본체 예외는 루프를 죽이지 않는다 (로깅 후 다음 틱).
- 스케줄러 틱은 별도 task + single-flight — 스케줄 직렬 실행(수십 초~분)이
  job 처리를 막지 않는다 (D1).
- spawn 한 task 참조는 완료까지 보유한다 (agent-webhook Check G1 GC 교훈).
"""
import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Awaitable, Callable, Optional

from src.application.agent_builder.schemas import RunAgentRequest
from src.domain.background_job.entity import BackgroundJob
from src.domain.background_job.policies import JobQueuePolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_RECONCILE_MESSAGE = "서버 재시작으로 실행이 중단되었습니다. 다시 요청해 주세요."
_SHUTDOWN_MESSAGE = "서버 종료로 실행이 중단되었습니다. 다시 요청해 주세요."
_NO_USER_MESSAGE = "사용자 정보를 찾을 수 없어 실행하지 못했습니다."

# AuthContext 재조립 콜러블 (user_id, request_id) -> AuthContext | None (D3)
AssembleAuthContext = Callable[[str, str], Awaitable[object]]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _failed_run_payload(job: BackgroundJob) -> SimpleNamespace:
    """실패 발송용 run-동형 페이로드 (FR-06) — answer=None 이 실패 신호."""
    return SimpleNamespace(
        query=job.query,
        answer=None,
        tools_used=[],
        session_id=job.session_id,
        run_id=None,
    )


class BackgroundJobWorker:
    def __init__(
        self,
        *,
        session_factory,
        job_repo_builder,
        run_agent_uc_builder,
        assemble_auth_context: AssembleAuthContext,
        logger: LoggerInterface,
        schedule_trigger_uc=None,
        outbound_dispatcher=None,
        poll_interval_sec: float = 5.0,
        schedule_tick_interval_sec: float = 30.0,
        max_concurrency: int = 2,
        enabled: bool = True,
        now_fn: Callable[[], datetime] = _utc_now,
    ) -> None:
        JobQueuePolicy.validate_concurrency(max_concurrency)
        self._session_factory = session_factory
        self._job_repo_builder = job_repo_builder
        self._run_agent_uc_builder = run_agent_uc_builder
        self._assemble_auth_context = assemble_auth_context
        self._schedule_trigger_uc = schedule_trigger_uc
        self._outbound_dispatcher = outbound_dispatcher
        self._logger = logger
        self._poll_interval = poll_interval_sec
        self._schedule_tick_interval = schedule_tick_interval_sec
        self._max_concurrency = max_concurrency
        self._enabled = enabled
        self._now_fn = now_fn

        self._loop_task: Optional[asyncio.Task] = None
        self._schedule_task: Optional[asyncio.Task] = None
        self._active_tasks: set[asyncio.Task] = set()
        self._last_schedule_tick: Optional[datetime] = None
        self._last_tick_at: Optional[datetime] = None
        self._last_error: Optional[str] = None

    # ── 수명 주기 ──────────────────────────────────────────────────

    def start(self) -> None:
        if not self._enabled:
            self._logger.info("background worker disabled — not started")
            return
        self._loop_task = asyncio.create_task(self._run())
        self._logger.info(
            "background worker started",
            poll_interval_sec=self._poll_interval,
            max_concurrency=self._max_concurrency,
        )

    async def stop(self) -> None:
        """shutdown (D7): 루프·활성 task 취소. failed 마킹은 각 task 의
        CancelledError 핸들러가 시도하고, 실패해도 다음 기동 reconcile 이 처리."""
        tasks = [
            t
            for t in (self._loop_task, self._schedule_task, *self._active_tasks)
            if t is not None and not t.done()
        ]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._logger.info("background worker stopped")

    async def drain(self) -> None:
        """활성 job task 완료 대기 (테스트·정상 종료 보조용)."""
        if self._active_tasks:
            await asyncio.gather(*list(self._active_tasks), return_exceptions=True)

    def status(self) -> dict:
        """루프 생존 관측 스냅샷 (§8)."""
        return {
            "enabled": self._enabled,
            "running": self._loop_task is not None and not self._loop_task.done(),
            "active_jobs": len(self._active_tasks),
            "last_tick_at": (
                self._last_tick_at.isoformat() if self._last_tick_at else None
            ),
            "last_error": self._last_error,
        }

    # ── 루프 본체 ──────────────────────────────────────────────────

    async def _run(self) -> None:
        await self.reconcile()
        while True:
            await self.tick_once()
            await asyncio.sleep(self._poll_interval)

    async def tick_once(self) -> None:
        """루프 1회전 — 예외는 삼키고 로깅 (루프 생존). 테스트 표면."""
        self._last_tick_at = self._now_fn()
        try:
            self._maybe_tick_schedules()
            await self._claim_and_spawn()
            self._last_error = None
        except Exception as e:
            self._last_error = str(e)[:512]
            self._logger.error(
                "background worker tick failed",
                exception=e,
                request_id="worker-tick",
            )

    async def reconcile(self) -> int:
        """기동 시 고아 running → failed 정리 (D6)."""
        request_id = f"worker-reconcile-{uuid.uuid4()}"
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    repo = self._job_repo_builder(session)
                    return await repo.reconcile_orphan_running(
                        _RECONCILE_MESSAGE, self._now_fn(), request_id
                    )
        except Exception as e:
            self._logger.error(
                "background worker reconcile failed",
                exception=e,
                request_id=request_id,
            )
            return 0

    # ── 스케줄러 틱 (D1) ───────────────────────────────────────────

    def _maybe_tick_schedules(self) -> None:
        if self._schedule_trigger_uc is None:
            return
        if self._schedule_task is not None and not self._schedule_task.done():
            return  # single-flight — 직전 틱 미완이면 skip
        now = self._now_fn()
        if (
            self._last_schedule_tick is not None
            and (now - self._last_schedule_tick).total_seconds()
            < self._schedule_tick_interval
        ):
            return
        self._last_schedule_tick = now
        self._schedule_task = asyncio.create_task(self._run_schedule_tick())

    async def _run_schedule_tick(self) -> None:
        request_id = f"worker-schedule-{uuid.uuid4()}"
        try:
            await self._schedule_trigger_uc.execute(request_id)
        except Exception as e:
            self._logger.error(
                "background worker schedule tick failed",
                exception=e,
                request_id=request_id,
            )

    # ── job claim·실행 (D2·D3·D8) ─────────────────────────────────

    async def _claim_and_spawn(self) -> None:
        slots = self._max_concurrency - len(self._active_tasks)
        if slots <= 0:
            return
        request_id = f"worker-claim-{uuid.uuid4()}"
        async with self._session_factory() as session:
            async with session.begin():
                repo = self._job_repo_builder(session)
                jobs = await repo.claim_queued(slots, self._now_fn(), request_id)
        for job in jobs:
            task = asyncio.create_task(self._execute_job(job))
            self._active_tasks.add(task)
            task.add_done_callback(self._active_tasks.discard)

    async def _execute_job(self, job: BackgroundJob) -> None:
        request_id = f"job-{job.id}"
        try:
            ctx = await self._assemble_auth_context(job.user_id, request_id)
            if ctx is None:
                await self._finish(
                    job.id, "failed", request_id, error_message=_NO_USER_MESSAGE
                )
                await self._dispatch_outbound(
                    job.agent_id, _failed_run_payload(job), request_id
                )
                return
            response = await self._run_agent(job, ctx, request_id)
            await self._finish(
                job.id,
                "success",
                request_id,
                session_id=response.session_id,
                run_id=response.run_id,
            )
            await self._dispatch_outbound(job.agent_id, response, request_id)
        except asyncio.CancelledError:
            await self._try_mark_shutdown_failed(job.id, request_id)
            raise
        except Exception as e:
            self._logger.error(
                "background job failed",
                exception=e,
                request_id=request_id,
                job_id=job.id,
            )
            await self._finish(
                job.id, "failed", request_id, error_message=str(e)
            )
            # Plan FR-06: 실패도 발송 대상 — answer=None 이 실패 신호
            await self._dispatch_outbound(
                job.agent_id, _failed_run_payload(job), request_id
            )

    async def _run_agent(self, job: BackgroundJob, ctx, request_id: str):
        """회차별 독립 세션으로 실행 (스케줄 _execute_agent 동형)."""
        async with self._session_factory() as session:
            async with session.begin():
                run_uc = self._run_agent_uc_builder(session)
                return await run_uc.execute(
                    job.agent_id,
                    RunAgentRequest(
                        query=job.query,
                        user_id=job.user_id,
                        session_id=job.session_id,
                    ),
                    request_id,
                    auth_ctx=ctx,
                    viewer_user_id=job.user_id,
                    viewer_department_ids=list(
                        getattr(ctx, "department_ids", []) or []
                    ),
                )

    async def _finish(
        self,
        job_id: str,
        status: str,
        request_id: str,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        error_message: str | None = None,
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                repo = self._job_repo_builder(session)
                await repo.finish(
                    job_id,
                    status,
                    self._now_fn(),
                    request_id,
                    session_id=session_id,
                    run_id=run_id,
                    error_message=error_message,
                )

    async def _try_mark_shutdown_failed(
        self, job_id: str, request_id: str
    ) -> None:
        """D7 — 취소 중 마킹 시도. 실패해도 다음 기동 reconcile 이 이중 방어."""
        try:
            await asyncio.shield(
                self._finish(
                    job_id,
                    "failed",
                    request_id,
                    error_message=_SHUTDOWN_MESSAGE,
                )
            )
        except Exception as e:
            self._logger.warning(
                "shutdown failed-marking skipped (reconcile will handle)",
                request_id=request_id,
                job_id=job_id,
                error=str(e)[:256],
            )

    async def _dispatch_outbound(self, agent_id: str, response, request_id: str):
        """D12 — dispatch 는 raise 금지 계약(D16)이지만 이중 방어."""
        if self._outbound_dispatcher is None:
            return
        try:
            await self._outbound_dispatcher.dispatch(
                agent_id, response, "job", request_id
            )
        except Exception as e:
            self._logger.error(
                "outbound dispatch hook failed",
                exception=e,
                request_id=request_id,
            )
