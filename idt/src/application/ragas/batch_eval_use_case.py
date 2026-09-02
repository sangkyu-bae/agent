"""배치 평가 UseCase — testset_id 실행·소유권·실행기 킥오프 (eval-hub Design A8)."""
import random
import uuid
from datetime import datetime, timezone

from src.application.ragas.schemas import BatchEvalRequest, BatchEvalResponse
from src.domain.ragas.entities import EvaluationRun
from src.domain.ragas.interfaces import EvaluationRepositoryInterface, EvaluatorInterface
from src.domain.ragas.policies import EvaluationPolicy
from src.domain.ragas.value_objects import EvalConfig, MetricType, TestCase
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class BatchEvaluationUseCase:
    def __init__(
        self,
        repository: EvaluationRepositoryInterface,
        evaluator: EvaluatorInterface,
        logger: LoggerInterface,
        executor=None,  # BatchEvalExecutor 싱글턴 — None이면 등록만 수행(pending 유지)
    ) -> None:
        self._repository = repository
        self._evaluator = evaluator
        self._logger = logger
        self._executor = executor

    async def execute(
        self,
        request: BatchEvalRequest,
        request_id: str,
        user_id: str | None = None,
        scope_user_id: str | None = None,
    ) -> BatchEvalResponse:
        config = EvalConfig(
            metrics=[MetricType(m) for m in request.metrics],
            top_k=request.top_k,
            sample_ratio=request.sample_ratio,
            llm_model=request.llm_model,
            agent_id=request.agent_id,
            collection_name=request.collection_name,
        )

        errors = EvaluationPolicy.validate_config(config)
        errors += EvaluationPolicy.validate_metrics_for_target(
            request.target_type, config.metrics
        )
        if errors:
            raise ValueError("; ".join(errors))

        raw_cases = await self._resolve_cases(request, request_id, scope_user_id)
        testcases = [
            TestCase(
                question=tc["question"],
                ground_truth=tc.get("ground_truth"),
                expected_contexts=tc.get("expected_contexts", []),
                metadata=tc.get("metadata", {}),
                # agent-model-benchmark §3.4: 테스트셋 cases는 JSON이라
                # 키 추가만으로 실린다 (DDL 변경 없음).
                expected_tools=tc.get("expected_tools"),
            )
            for tc in raw_cases
        ]

        case_errors = EvaluationPolicy.validate_testcases(testcases, config)
        if case_errors:
            raise ValueError("; ".join(case_errors))

        if config.sample_ratio < 1.0:
            sample_size = max(1, int(len(testcases) * config.sample_ratio))
            testcases = random.sample(testcases, sample_size)

        run = EvaluationRun(
            id=str(uuid.uuid4()),
            eval_type="batch",
            target_type=request.target_type,
            target_id=request.agent_id,
            user_id=user_id,
            status="pending",
            total_cases=len(testcases),
            config={
                "metrics": request.metrics,
                "top_k": request.top_k,
                "llm_model": request.llm_model,
                "testset_id": request.testset_id,
                "agent_id": request.agent_id,
                "collection_name": request.collection_name,
                "sample_ratio": request.sample_ratio,
            },
            created_at=datetime.now(timezone.utc),
        )
        await self._repository.save_run(run, request_id)

        if self._executor is not None:
            self._executor.kickoff(
                run_id=run.id,
                target_type=request.target_type,
                testcases=testcases,
                config=config,
                user_id=user_id,
                request_id=request_id,
            )

        return BatchEvalResponse(
            run_id=run.id,
            status=run.status,
            total_cases=run.total_cases,
            message="배치 평가가 등록되었습니다.",
        )

    async def _resolve_cases(
        self,
        request: BatchEvalRequest,
        request_id: str,
        scope_user_id: str | None,
    ) -> list[dict]:
        """testset_id와 인라인 testcases는 배타 — 정확히 하나만 허용."""
        has_testset = bool(request.testset_id)
        has_inline = bool(request.testcases)
        if has_testset == has_inline:
            raise ValueError(
                "testset_id와 testcases 중 정확히 하나만 제공해야 합니다"
            )
        if has_inline:
            return request.testcases

        testset = await self._repository.get_testset(request.testset_id, request_id)
        if testset is None or (
            scope_user_id is not None and testset.get("user_id") != scope_user_id
        ):
            raise ValueError("테스트셋을 찾을 수 없습니다")  # 타인 자원 존재 은닉
        return testset.get("cases") or []
