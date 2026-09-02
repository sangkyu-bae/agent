"""SweepExecutor — 모델을 하나씩 순차 실행하는 오케스트레이터.

Design Ref: D7 — 병렬로 돌리면 모델끼리 지연 측정을 오염시키고 provider
rate limit에 걸린다. 느리더라도 순차가 옳다.
Design Ref: D12 — 개별 run 실패는 해당 모델 행만 실패로 남기고 스윕은 계속한다.
"""
import asyncio
from datetime import datetime, timezone

from src.application.ragas.batch_executor import BatchEvalExecutor
from src.domain.eval_sweep.entity import EvaluationSweep
from src.domain.eval_sweep.interfaces import SweepRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.ragas.value_objects import EvalConfig, TestCase

_TARGET_TYPE = "agent"


class SweepExecutor:
    def __init__(
        self,
        batch_executor: BatchEvalExecutor,
        sweep_repo_builder,
        session_factory,
        logger: LoggerInterface,
    ) -> None:
        self._batch = batch_executor
        self._sweep_repo_builder = sweep_repo_builder
        self._session_factory = session_factory
        self._logger = logger
        self._tasks: set[asyncio.Task] = set()

    def kickoff(
        self,
        sweep: EvaluationSweep,
        run_ids: list[str],
        testcases: list[TestCase],
        base_config: EvalConfig,
        user_id: str | None,
        request_id: str,
    ) -> None:
        """백그라운드 태스크로 스윕을 시작한다 (202 즉시 반환용)."""
        task = asyncio.create_task(
            self._run_guarded(
                sweep, run_ids, testcases, base_config, user_id, request_id
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run_guarded(
        self,
        sweep: EvaluationSweep,
        run_ids: list[str],
        testcases: list[TestCase],
        base_config: EvalConfig,
        user_id: str | None,
        request_id: str,
    ) -> None:
        try:
            await self._run(
                sweep, run_ids, testcases, base_config, user_id, request_id
            )
        except Exception as e:
            self._logger.exception(
                "Sweep orchestration crashed",
                request_id=request_id,
                sweep_id=sweep.id,
            )
            sweep.mark_failed(str(e)[:512], datetime.now(timezone.utc))
            await self._persist(sweep, request_id)

    async def _run(
        self,
        sweep: EvaluationSweep,
        run_ids: list[str],
        testcases: list[TestCase],
        base_config: EvalConfig,
        user_id: str | None,
        request_id: str,
    ) -> None:
        sweep.mark_running()
        await self._persist(sweep, request_id)

        for run_id, model_id in zip(run_ids, sweep.model_ids):
            await self._run_one_model(
                run_id, model_id, testcases, base_config, user_id, request_id
            )
            sweep.mark_run_completed(datetime.now(timezone.utc))
            await self._persist(sweep, request_id)

        self._logger.info(
            "Sweep finished",
            request_id=request_id,
            sweep_id=sweep.id,
            status=sweep.status,
        )

    async def _run_one_model(
        self,
        run_id: str,
        model_id: str,
        testcases: list[TestCase],
        base_config: EvalConfig,
        user_id: str | None,
        request_id: str,
    ) -> None:
        """모델 1개분 실행 (D12 부분 실패 격리).

        run_now(=BatchEvalExecutor._run_guarded)가 이미 예외를 삼키지만, 여기서
        한 번 더 막는다. 이 가드가 없으면 run_now가 어떤 이유로든 예외를 흘렸을 때
        루프가 끊겨 **뒤에 남은 모델들이 아예 실행되지 않는다** — 부분 결과라도
        비교는 성립하므로 한 모델의 실패가 나머지를 죽이면 안 된다.
        """
        self._logger.info(
            "Sweep model run start",
            request_id=request_id,
            run_id=run_id,
            llm_model_id=model_id,
        )
        config = _with_model(base_config, model_id)
        try:
            await self._batch.run_now(
                run_id, _TARGET_TYPE, testcases, config, user_id, request_id
            )
        except Exception:
            self._logger.exception(
                "Sweep model run failed — 나머지 모델은 계속 실행한다",
                request_id=request_id,
                run_id=run_id,
                llm_model_id=model_id,
            )

    async def _persist(self, sweep: EvaluationSweep, request_id: str) -> None:
        """진행 상태를 즉시 반영한다 — 프론트 폴링이 진행률을 읽어간다.

        백그라운드 태스크이므로 run 단위로 세션을 새로 연다
        (SessionScopedEvalRunStore 선례 / docs/rules/db-session.md).
        """
        async with self._session_factory() as session:
            async with session.begin():
                repo = self._sweep_repo_builder(session)
                await repo.update(sweep, request_id)


def _with_model(config: EvalConfig, model_id: str) -> EvalConfig:
    """피평가 모델만 바꾼 설정 사본 — EvalConfig는 frozen이라 replace가 필요하다."""
    from dataclasses import replace

    return replace(config, llm_model_id_override=model_id)
