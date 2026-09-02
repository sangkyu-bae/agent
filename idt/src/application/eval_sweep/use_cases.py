"""모델 스윕 UseCase — 비용추정 / 생성 / 조회 / 삭제.

Design Ref: §4.2 엔드포인트 5종의 흐름 제어.
비즈니스 규칙(모델 수 제한·도구 F1)은 domain/eval_sweep/policies.py가 소유한다.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from src.application.eval_sweep.schemas import (
    CreateSweepRequest,
    CreateSweepResponse,
    PerModelEstimate,
    SweepDetailResponse,
    SweepEstimateRequest,
    SweepEstimateResponse,
    SweepRowResponse,
    SweepSummaryResponse,
)
from src.domain.eval_sweep.entity import EvaluationSweep
from src.domain.eval_sweep.policies import SweepPolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.ragas.entities import EvaluationRun
from src.domain.ragas.value_objects import EvalConfig, MetricType, TestCase

# 실행 이력이 없어 실측 평균을 못 구할 때 쓰는 보수적 가정치 (§4.2 basis).
_FALLBACK_PROMPT_TOKENS = 2000
_FALLBACK_COMPLETION_TOKENS = 500
# judge 채점 1회가 소비하는 대략적 토큰 (질문+답변+컨텍스트 재입력).
_JUDGE_TOKENS_PER_CASE = 1500
# 케이스 1건당 예상 소요 초 — 예상 소요시간 산출용.
_SECONDS_PER_CASE = 14


class EstimateSweepCostUseCase:
    """실행 전 예상 비용을 낸다 (FR-05).

    사용자가 '실행' 을 누르기 전에 금액을 보여주는 것이 목적이므로
    부수효과가 없어야 한다 — 아무것도 저장하지 않는다.
    """

    def __init__(
        self,
        eval_repo,
        llm_model_repo,
        token_stats_provider,
        logger: LoggerInterface,
    ) -> None:
        self._eval_repo = eval_repo
        self._llm_model_repo = llm_model_repo
        self._token_stats = token_stats_provider
        self._logger = logger

    async def execute(
        self, request: SweepEstimateRequest, request_id: str
    ) -> SweepEstimateResponse:
        case_count = await _load_case_count(
            self._eval_repo, request.testset_id, request_id
        )
        stats = await self._token_stats(request.agent_id, request_id)
        prompt_tokens = stats.get("avg_prompt_tokens") or _FALLBACK_PROMPT_TOKENS
        completion_tokens = (
            stats.get("avg_completion_tokens") or _FALLBACK_COMPLETION_TOKENS
        )

        per_model: list[PerModelEstimate] = []
        for model_id in request.model_ids:
            model = await self._llm_model_repo.find_by_id(model_id, request_id)
            per_model.append(
                PerModelEstimate(
                    llm_model_id=model_id,
                    display_name=getattr(model, "display_name", model_id),
                    estimated_cost_usd=_cost_of(
                        model, prompt_tokens, completion_tokens, case_count
                    ),
                )
            )

        judge_cost = await self._judge_cost(
            request.judge_llm_model_id,
            case_count * max(len(request.model_ids), 1),
            request_id,
        )
        total = sum((p.estimated_cost_usd for p in per_model), Decimal("0")) + judge_cost

        return SweepEstimateResponse(
            case_count=case_count,
            model_count=len(request.model_ids),
            total_calls=case_count * len(request.model_ids),
            estimated_cost_usd=total,
            estimated_minutes=_estimated_minutes(case_count, len(request.model_ids)),
            basis={
                "source": stats.get("source", "fallback_constant"),
                "avg_prompt_tokens": prompt_tokens,
                "avg_completion_tokens": completion_tokens,
                "sample_size": stats.get("sample_size", 0),
                "judge_cost_usd": str(judge_cost),
            },
            per_model=per_model,
        )

    async def _judge_cost(
        self, judge_model_id: str | None, total_cases: int, request_id: str
    ) -> Decimal:
        """judge 채점 비용을 빠뜨리면 추정이 실제보다 크게 낮아진다 (Plan R-3)."""
        if not judge_model_id:
            return Decimal("0")
        model = await self._llm_model_repo.find_by_id(judge_model_id, request_id)
        return _cost_of(model, _JUDGE_TOKENS_PER_CASE, 0, total_cases)


class CreateSweepUseCase:
    """스윕과 하위 run N건을 만들고 순차 실행을 시작한다 (FR-03/FR-04)."""

    def __init__(
        self,
        sweep_repo,
        eval_repo,
        llm_model_repo,
        executor,
        estimator: EstimateSweepCostUseCase,
        logger: LoggerInterface,
    ) -> None:
        self._sweep_repo = sweep_repo
        self._eval_repo = eval_repo
        self._llm_model_repo = llm_model_repo
        self._executor = executor
        self._estimator = estimator
        self._logger = logger

    async def execute(
        self,
        request: CreateSweepRequest,
        request_id: str,
        user_id: str | None = None,
    ) -> CreateSweepResponse:
        testset = await _load_testset(self._eval_repo, request.testset_id, request_id)
        raw_cases = testset.get("cases") or []
        metrics = [MetricType(m) for m in request.metrics]

        errors = SweepPolicy.validate(
            model_ids=request.model_ids,
            judge_llm_model_id=request.judge_llm_model_id,
            metrics=metrics,
            testset_case_count=len(raw_cases),
        )
        errors += await self._validate_models_active(request, request_id)
        if errors:
            raise ValueError("; ".join(errors))

        estimate = await self._estimator.execute(
            SweepEstimateRequest(
                agent_id=request.agent_id,
                testset_id=request.testset_id,
                model_ids=request.model_ids,
                judge_llm_model_id=request.judge_llm_model_id,
                metrics=request.metrics,
            ),
            request_id,
        )

        now = datetime.now(timezone.utc)
        sweep = EvaluationSweep(
            id=str(uuid.uuid4()),
            name=request.name,
            agent_id=request.agent_id,
            testset_id=request.testset_id,
            judge_llm_model_id=request.judge_llm_model_id,
            model_ids=list(request.model_ids),
            metrics=list(request.metrics),
            temperature=SweepPolicy.FIXED_TEMPERATURE,
            status="pending",
            total_runs=SweepPolicy.total_runs(request.model_ids),
            estimated_cost_usd=estimate.estimated_cost_usd,
            user_id=user_id,
            created_at=now,
        )
        await self._sweep_repo.save(sweep, request_id)

        run_ids = await self._create_runs(sweep, len(raw_cases), user_id, request_id)
        self._executor.kickoff(
            sweep,
            run_ids,
            _to_testcases(raw_cases),
            _base_config(sweep, metrics),
            user_id,
            request_id,
        )

        return CreateSweepResponse(
            sweep_id=sweep.id,
            status=sweep.status,
            total_runs=sweep.total_runs,
            estimated_cost_usd=sweep.estimated_cost_usd,
            message=(
                f"스윕이 시작되었습니다. 모델 {sweep.total_runs}개를 순차 실행합니다."
            ),
        )

    async def _validate_models_active(
        self, request: CreateSweepRequest, request_id: str
    ) -> list[str]:
        """비활성·미존재 모델을 실행 전에 걸러낸다 (§6.1)."""
        errors: list[str] = []
        for model_id in [*request.model_ids, request.judge_llm_model_id]:
            if not model_id:
                continue
            model = await self._llm_model_repo.find_by_id(model_id, request_id)
            if model is None:
                errors.append(f"모델을 찾을 수 없습니다: {model_id}")
            elif not model.is_active:
                errors.append(f"비활성 모델은 사용할 수 없습니다: {model.display_name}")
        return errors

    async def _create_runs(
        self,
        sweep: EvaluationSweep,
        case_count: int,
        user_id: str | None,
        request_id: str,
    ) -> list[str]:
        run_ids: list[str] = []
        for model_id in sweep.model_ids:
            run = EvaluationRun(
                id=str(uuid.uuid4()),
                eval_type="batch",
                target_type="agent",
                target_id=sweep.agent_id,
                user_id=user_id,
                # §3.3: 모델 차원을 run에 부여 — 매트릭스 집계의 축이다.
                sweep_id=sweep.id,
                llm_model_id=model_id,
                status="pending",
                total_cases=case_count,
                config={
                    "sweep_id": sweep.id,
                    "llm_model_id": model_id,
                    "judge_llm_model_id": sweep.judge_llm_model_id,
                    "metrics": sweep.metrics,
                    "testset_id": sweep.testset_id,
                    "agent_id": sweep.agent_id,
                    "temperature": sweep.temperature,
                },
                created_at=datetime.now(timezone.utc),
            )
            saved = await self._eval_repo.save_run(run, request_id)
            run_ids.append(saved.id)
        return run_ids


class GetSweepDetailUseCase:
    """스윕 상세 + 모델별 4축 집계 (FR-09)."""

    def __init__(
        self,
        sweep_repo,
        llm_model_repo,
        logger: LoggerInterface,
        agent_repo=None,
        eval_repo=None,
    ) -> None:
        self._sweep_repo = sweep_repo
        self._llm_model_repo = llm_model_repo
        # G-2: 실험 조건 표시용. 미주입이면 이름 필드만 비고 나머지는 정상 동작한다.
        self._agent_repo = agent_repo
        self._eval_repo = eval_repo
        self._logger = logger

    async def execute(
        self, sweep_id: str, request_id: str, scope_user_id: str | None = None
    ) -> SweepDetailResponse:
        sweep = await self._sweep_repo.get(sweep_id, request_id)
        _ensure_visible(sweep, scope_user_id)

        rows = [
            await self._to_row(r, request_id)
            for r in await self._sweep_repo.get_rows(sweep_id, request_id)
        ]
        context = await self._describe_conditions(sweep, request_id)
        return SweepDetailResponse(
            **_summary_fields(sweep),
            model_ids=sweep.model_ids,
            metrics=sweep.metrics,
            rows=rows,
            # G-1: 행별 실제 비용의 합. 측정된 행이 하나도 없으면 None(N/A)이다.
            actual_cost_usd=_sum_costs(rows),
            **context,
        )

    async def _describe_conditions(self, sweep, request_id: str) -> dict:
        """에이전트명·테스트셋명·케이스 수 (G-2).

        조회 실패는 상세 조회 전체를 실패시키지 않는다 — 이름은 부가 정보다.
        """
        result: dict = {"agent_name": None, "testset_name": None, "case_count": 0}
        if self._agent_repo is not None:
            agent = await self._safe(
                self._agent_repo.find_by_id(sweep.agent_id, request_id), request_id
            )
            result["agent_name"] = getattr(agent, "name", None)
        if self._eval_repo is not None:
            testset = await self._safe(
                self._eval_repo.get_testset(sweep.testset_id, request_id), request_id
            )
            if testset:
                result["testset_name"] = testset.get("name")
                result["case_count"] = len(testset.get("cases") or [])
        return result

    async def _safe(self, coro, request_id: str):
        try:
            return await coro
        except Exception as e:
            self._logger.warning(
                "스윕 실험 조건 조회 실패 — 이름 없이 진행",
                request_id=request_id,
                exception=e,
            )
            return None

    async def _to_row(self, row, request_id: str) -> SweepRowResponse:
        name = None
        if row.llm_model_id:
            model = await self._llm_model_repo.find_by_id(row.llm_model_id, request_id)
            name = getattr(model, "display_name", None)
        return SweepRowResponse(
            run_id=row.run_id,
            llm_model_id=row.llm_model_id,
            llm_model_name=name,
            status=row.status,
            quality=row.quality,
            cost_usd=row.cost_usd,
            latency_p50_ms=row.latency_p50_ms,
            latency_p95_ms=row.latency_p95_ms,
            tool_f1=row.tool_f1,
            measured_cases=row.measured_cases,
            failed_cases=row.failed_cases,
            error_message=row.error_message,
        )


class ListSweepsUseCase:
    def __init__(self, sweep_repo, logger: LoggerInterface) -> None:
        self._sweep_repo = sweep_repo
        self._logger = logger

    async def execute(
        self,
        limit: int,
        offset: int,
        request_id: str,
        scope_user_id: str | None = None,
    ) -> tuple[list[SweepSummaryResponse], int]:
        sweeps, total = await self._sweep_repo.list_by_user(
            scope_user_id, limit, offset, request_id
        )
        return [SweepSummaryResponse(**_summary_fields(s)) for s in sweeps], total


class DeleteSweepUseCase:
    def __init__(self, sweep_repo, logger: LoggerInterface) -> None:
        self._sweep_repo = sweep_repo
        self._logger = logger

    async def execute(
        self, sweep_id: str, request_id: str, scope_user_id: str | None = None
    ) -> None:
        sweep = await self._sweep_repo.get(sweep_id, request_id)
        _ensure_visible(sweep, scope_user_id)
        await self._sweep_repo.delete(sweep_id, request_id)


# ── 공통 헬퍼 ────────────────────────────────────────────────────────


def _ensure_visible(sweep, scope_user_id: str | None) -> None:
    """미소유 스윕은 403이 아니라 404로 은닉한다 (§7, eval_router 선례).

    403은 '존재는 한다'는 정보를 흘린다.
    """
    if sweep is None:
        raise ValueError("스윕을 찾을 수 없습니다")
    if scope_user_id is not None and sweep.user_id != scope_user_id:
        raise ValueError("스윕을 찾을 수 없습니다")


def _sum_costs(rows) -> Decimal | None:
    """실제 비용 합계 (G-1). 측정된 행이 없으면 None — 0과 구분한다 (§3.5)."""
    costs = [r.cost_usd for r in rows if r.cost_usd is not None]
    if not costs:
        return None
    return sum(costs, Decimal("0"))


def _summary_fields(sweep) -> dict:
    return {
        "id": sweep.id,
        "name": sweep.name,
        "agent_id": sweep.agent_id,
        "testset_id": sweep.testset_id,
        "judge_llm_model_id": sweep.judge_llm_model_id,
        "temperature": sweep.temperature,
        "status": sweep.status,
        "total_runs": sweep.total_runs,
        "completed_runs": sweep.completed_runs,
        "estimated_cost_usd": sweep.estimated_cost_usd,
        "created_at": sweep.created_at,
        "completed_at": sweep.completed_at,
    }


async def _load_testset(eval_repo, testset_id: str, request_id: str) -> dict:
    testset = await eval_repo.get_testset(testset_id, request_id)
    if testset is None:
        raise ValueError("테스트셋을 찾을 수 없습니다")
    return testset


async def _load_case_count(eval_repo, testset_id: str, request_id: str) -> int:
    testset = await _load_testset(eval_repo, testset_id, request_id)
    return len(testset.get("cases") or [])


def _to_testcases(raw_cases: list[dict]) -> list[TestCase]:
    return [
        TestCase(
            question=c["question"],
            ground_truth=c.get("ground_truth"),
            expected_contexts=c.get("expected_contexts", []),
            metadata=c.get("metadata", {}),
            expected_tools=c.get("expected_tools"),
        )
        for c in raw_cases
    ]


def _base_config(sweep: EvaluationSweep, metrics: list[MetricType]) -> EvalConfig:
    """스윕 전 모델이 공유하는 설정. 모델 id만 SweepExecutor가 바꿔 끼운다."""
    return EvalConfig(
        metrics=metrics,
        agent_id=sweep.agent_id,
        judge_llm_model=sweep.judge_llm_model_id,
        temperature_override=sweep.temperature,
        persist_conversation=False,
    )


def _cost_of(model, prompt_tokens: int, completion_tokens: int, cases: int) -> Decimal:
    """단가 미등록 모델(self-host 등)은 0으로 계산한다 — 추정 실패가 아니다."""
    if model is None or cases <= 0:
        return Decimal("0")
    in_price = getattr(model, "input_price_per_1k_usd", None) or Decimal("0")
    out_price = getattr(model, "output_price_per_1k_usd", None) or Decimal("0")
    per_case = (
        Decimal(prompt_tokens) / 1000 * Decimal(in_price)
        + Decimal(completion_tokens) / 1000 * Decimal(out_price)
    )
    return (per_case * cases).quantize(Decimal("0.000001"))


def _estimated_minutes(case_count: int, model_count: int) -> int:
    total_seconds = case_count * model_count * _SECONDS_PER_CASE
    return max(1, round(total_seconds / 60))
