"""BatchEvalExecutor — 배치 평가 백그라운드 실행기 (eval-hub Design §2.4).

애플리케이션 싱글턴. kickoff()는 sync 즉시 반환 — asyncio.create_task + _tasks
보관(GC 방지, section_summary launcher D11 패턴). DB 접근은 EvalRunStoreInterface
(연산마다 독립 짧은 세션) 경유.

요청 트랜잭션 커밋 전에 태스크가 먼저 돌 수 있으므로, run 조회는
run_fetch_retries회 재시도 후 포기한다.
"""
import asyncio
import uuid
from datetime import datetime, timezone

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.ragas.entities import EvaluationResult, EvaluationRun
from src.domain.ragas.interfaces import (
    EvalRunStoreInterface,
    EvaluatorInterface,
    TargetExecutorInterface,
)
from src.domain.eval_sweep.policies import ToolAccuracyPolicy
from src.domain.ragas.policies import RAGAS_METRICS
from src.domain.ragas.value_objects import EvalConfig, TestCase


class BatchEvalExecutor:
    def __init__(
        self,
        store: EvalRunStoreInterface,
        evaluator: EvaluatorInterface,
        target_executor: TargetExecutorInterface,
        logger: LoggerInterface,
        run_fetch_retries: int = 10,
        retry_delay: float = 1.0,
    ) -> None:
        self._store = store
        self._evaluator = evaluator
        self._target_executor = target_executor
        self._logger = logger
        self._run_fetch_retries = run_fetch_retries
        self._retry_delay = retry_delay
        self._tasks: set[asyncio.Task] = set()

    def kickoff(
        self,
        run_id: str,
        target_type: str,
        testcases: list[TestCase],
        config: EvalConfig,
        user_id: str | None,
        request_id: str,
    ) -> None:
        task = asyncio.create_task(
            self._run_guarded(
                run_id, target_type, testcases, config, user_id, request_id
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def run_now(
        self,
        run_id: str,
        target_type: str,
        testcases: list[TestCase],
        config: EvalConfig,
        user_id: str | None,
        request_id: str,
    ) -> None:
        """run 1건을 **await 가능하게** 실행한다 (agent-model-benchmark D7).

        kickoff은 fire-and-forget이라 순차 오케스트레이션에 쓸 수 없다. SweepExecutor는
        모델을 하나씩 끝내야 지연 측정이 오염되지 않으므로 이 진입점을 쓴다.
        예외는 _run_guarded가 삼켜 개별 run 실패가 스윕을 죽이지 않는다 (D12).
        """
        await self._run_guarded(
            run_id, target_type, testcases, config, user_id, request_id
        )

    async def _run_guarded(
        self,
        run_id: str,
        target_type: str,
        testcases: list[TestCase],
        config: EvalConfig,
        user_id: str | None,
        request_id: str,
    ) -> None:
        try:
            await self._run(
                run_id, target_type, testcases, config, user_id, request_id
            )
        except Exception as e:
            self._logger.error(
                "Batch eval task crashed",
                exception=e,
                request_id=request_id,
                run_id=run_id,
            )

    async def _run(
        self,
        run_id: str,
        target_type: str,
        testcases: list[TestCase],
        config: EvalConfig,
        user_id: str | None,
        request_id: str,
    ) -> None:
        run = await self._wait_for_run(run_id, request_id)
        if run is None:
            self._logger.error(
                "Batch eval run not visible after retries",
                request_id=request_id,
                run_id=run_id,
            )
            return

        run.status = "running"
        await self._store.update_run(run, request_id)

        try:
            results = [
                await self._evaluate_case(run_id, target_type, config, tc, user_id, request_id)
                for tc in testcases
            ]
            if results:
                await self._store.save_results_bulk(results, request_id)
            run.mark_completed(datetime.now(timezone.utc))
            await self._store.update_run(run, request_id)
        except Exception as e:
            self._logger.exception(
                "Batch evaluation failed", request_id=request_id, run_id=run_id
            )
            run.mark_failed(str(e), datetime.now(timezone.utc))
            await self._store.update_run(run, request_id)

    async def _evaluate_case(
        self,
        run_id: str,
        target_type: str,
        config: EvalConfig,
        tc: TestCase,
        user_id: str | None,
        request_id: str,
    ) -> EvaluationResult:
        execution = await self._target_executor.execute(
            target_type, config, tc, user_id, request_id
        )

        ragas_metric_names = [
            m.value for m in config.metrics if m in RAGAS_METRICS
        ]
        scores: dict[str, float | None] = {}
        if ragas_metric_names:
            scores = await self._evaluator.evaluate(
                question=tc.question,
                answer=execution.answer,
                contexts=execution.contexts,
                ground_truth=tc.ground_truth,
                metrics=ragas_metric_names,
                request_id=request_id,
                # agent-model-benchmark D4: 실행에 박제된 judge로 채점한다.
                judge_model=config.judge_llm_model,
            )
        # D6: expected_tools가 있는 케이스만 도구 지표를 붙인다. 기재가 없으면
        # 키 자체를 만들지 않는다 — 부재도 N/A이고, rag/retrieval 결과에 의미
        # 없는 tool_* 키를 남기지 않기 위함이다 (FR-15).
        scores = {**scores, **execution.extra_scores}
        if tc.expected_tools:
            scores.update(
                ToolAccuracyPolicy.score(tc.expected_tools, execution.tools_used or [])
            )

        return EvaluationResult(
            id=str(uuid.uuid4()),
            run_id=run_id,
            question=tc.question,
            answer=execution.answer,
            contexts=execution.contexts,
            ground_truth=tc.ground_truth,
            metrics=scores,
            ai_run_id=execution.ai_run_id,
            tools_used=execution.tools_used,
            created_at=datetime.now(timezone.utc),
        )

    async def _wait_for_run(
        self, run_id: str, request_id: str
    ) -> EvaluationRun | None:
        for attempt in range(self._run_fetch_retries):
            run = await self._store.get_run(run_id, request_id)
            if run is not None:
                return run
            if attempt < self._run_fetch_retries - 1:
                await asyncio.sleep(self._retry_delay)
        return None
