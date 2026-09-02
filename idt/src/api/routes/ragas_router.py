"""RAGAS 평가 REST API — 인증·소유권 스코프 포함 (eval-hub Design §2.2~2.3).

모든 엔드포인트 인증 필수. 일반 사용자는 본인 소유 자원만(scope=본인),
admin은 전체(scope=None). 타인/미존재 자원은 404로 존재를 은닉한다.
"""
import uuid
from datetime import datetime
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from pydantic import BaseModel, Field

from src.application.eval_sweep.schemas import (
    CreateSweepRequest,
    CreateSweepResponse,
    SweepDetailResponse,
    SweepEstimateRequest,
    SweepEstimateResponse,
)
from src.domain.auth.entities import User
from src.domain.ragas.policies import (
    METRICS_REQUIRING_GROUND_TRUTH,
    TARGET_METRICS,
)
from src.domain.ragas.value_objects import MetricType
from src.interfaces.dependencies.auth import get_current_user

router = APIRouter(prefix="/api/ragas", tags=["RAGAS Evaluation"])


# ── DI 플레이스홀더 (main.py에서 override) ──────────────────────────

def get_batch_eval_use_case():
    raise NotImplementedError


def get_realtime_eval_use_case():
    raise NotImplementedError


def get_eval_result_use_case():
    raise NotImplementedError


def get_testset_use_case():
    raise NotImplementedError


def get_testset_generate_use_case():
    raise NotImplementedError


# agent-model-benchmark module-5: 모델 스윕 UseCase DI 플레이스홀더.

def get_create_sweep_use_case():
    raise NotImplementedError


def get_estimate_sweep_use_case():
    raise NotImplementedError


def get_sweep_detail_use_case():
    raise NotImplementedError


def get_list_sweeps_use_case():
    raise NotImplementedError


def get_delete_sweep_use_case():
    raise NotImplementedError


def _scope(user: User) -> str | None:
    """admin=None(전체), 그 외=본인 id 문자열."""
    return None if user.role.value == "admin" else str(user.id)


def _raise_eval_error(exc: ValueError) -> None:
    msg = str(exc)
    raise HTTPException(status_code=404 if "찾을 수 없" in msg else 422, detail=msg)


# ── Request/Response 스키마 ──────────────────────────────────────────

class BatchEvalRequestBody(BaseModel):
    target_type: str = Field(..., pattern="^(rag|agent|retrieval)$")
    metrics: list[str]
    testcases: list[dict[str, Any]] = Field(default_factory=list)
    testset_id: str | None = None  # testcases와 배타 — 정확히 하나만 제공
    top_k: int = Field(5, ge=1, le=100)
    sample_ratio: float = Field(1.0, gt=0.0, le=1.0)
    llm_model: str = "gpt-4o-mini"
    agent_id: str | None = None
    collection_name: str | None = None


class BatchEvalResponseBody(BaseModel):
    run_id: str
    status: str
    total_cases: int
    message: str


class RealtimeEvalRequestBody(BaseModel):
    question: str
    answer: str
    contexts: list[str]
    ground_truth: str | None = None
    metrics: list[str] = Field(default=["faithfulness", "answer_relevancy"])
    target_type: str = Field("rag", pattern="^(rag|agent|retrieval)$")


class RealtimeEvalResponseBody(BaseModel):
    result_id: str
    scores: dict[str, float]


class EvalRunDetailBody(BaseModel):
    id: str
    eval_type: str
    target_type: str
    status: str
    total_cases: int
    created_at: datetime
    completed_at: datetime | None
    summary: dict[str, float]
    error_message: str | None = None
    config: dict = Field(default_factory=dict)
    # agent-model-benchmark §4.3 / G-10: 스윕 소속 식별 (단독 실행이면 None)
    sweep_id: str | None = None
    llm_model_id: str | None = None


class EvalResultItemBody(BaseModel):
    id: str
    question: str
    answer: str
    ground_truth: str | None
    contexts: list[str]
    scores: dict[str, float]
    created_at: datetime


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    limit: int
    offset: int


class TestsetUploadRequestBody(BaseModel):
    name: str = Field(..., max_length=200)
    description: str = ""
    cases: list[dict[str, Any]]


class TestsetResponseBody(BaseModel):
    id: str
    name: str
    description: str
    case_count: int
    created_at: datetime
    user_id: str | None = None


class TestsetDetailResponseBody(TestsetResponseBody):
    cases: list[dict[str, Any]] = Field(default_factory=list)


class GeneratedDraftResponseBody(BaseModel):
    source_filename: str
    items: list[dict[str, Any]]


class MetricInfoBody(BaseModel):
    key: str
    name: str
    description: str
    target_types: list[str]
    requires_ground_truth: bool


def _to_run_body(detail) -> EvalRunDetailBody:
    return EvalRunDetailBody(
        id=detail.id,
        eval_type=detail.eval_type,
        target_type=detail.target_type,
        status=detail.status,
        total_cases=detail.total_cases,
        created_at=detail.created_at,
        completed_at=detail.completed_at,
        summary=detail.summary,
        error_message=detail.error_message,
        config=detail.config,
        sweep_id=getattr(detail, "sweep_id", None),
        llm_model_id=getattr(detail, "llm_model_id", None),
    )


def _to_result_body(item) -> EvalResultItemBody:
    return EvalResultItemBody(
        id=item.id,
        question=item.question,
        answer=item.answer,
        ground_truth=item.ground_truth,
        contexts=item.contexts,
        scores=item.scores,
        created_at=item.created_at,
    )


def _to_testset_body(resp) -> TestsetResponseBody:
    return TestsetResponseBody(
        id=resp.id,
        name=resp.name,
        description=resp.description,
        case_count=resp.case_count,
        created_at=resp.created_at,
        user_id=resp.user_id,
    )


# ── 메트릭 카탈로그 (A7) ─────────────────────────────────────────────

# 화면 표시용 한글 이름·설명 — 적용 대상·GT 필요 여부의 SoT는 domain policies
_METRIC_DISPLAY: dict[MetricType, tuple[str, str]] = {
    MetricType.FAITHFULNESS: (
        "충실성 (Faithfulness)",
        "답변이 검색된 문서 근거에서 벗어나지 않는지 측정합니다. 환각이 많을수록 점수가 낮아집니다.",
    ),
    MetricType.ANSWER_RELEVANCY: (
        "답변 관련성 (Answer Relevancy)",
        "답변이 질문의 의도에 얼마나 부합하는지 측정합니다.",
    ),
    MetricType.CONTEXT_PRECISION: (
        "컨텍스트 정밀도 (Context Precision)",
        "검색된 문서 중 질문과 관련 있는 문서의 비율을 측정합니다.",
    ),
    MetricType.CONTEXT_RECALL: (
        "컨텍스트 재현율 (Context Recall)",
        "정답에 필요한 근거가 검색 결과에 얼마나 포함됐는지 측정합니다.",
    ),
    MetricType.ANSWER_CORRECTNESS: (
        "답변 정확성 (Answer Correctness)",
        "답변이 정답(ground truth)과 사실적으로 일치하는지 측정합니다.",
    ),
    MetricType.ANSWER_SIMILARITY: (
        "답변 유사도 (Answer Similarity)",
        "답변과 정답의 의미적 유사도를 임베딩 기반으로 측정합니다.",
    ),
    MetricType.HIT_RATE: (
        "적중률 (Hit Rate)",
        "기대 근거 문서가 검색 결과에 1건이라도 포함되면 적중으로 봅니다.",
    ),
    MetricType.MRR: (
        "MRR (Mean Reciprocal Rank)",
        "첫 번째 관련 문서가 얼마나 상위에 검색되는지 측정합니다.",
    ),
    MetricType.NDCG: (
        "NDCG",
        "검색 결과 상위권에 관련 문서가 몰려 있을수록 높은 점수를 줍니다.",
    ),
}


@router.get("/metrics", response_model=list[MetricInfoBody])
async def list_metrics(
    user: User = Depends(get_current_user),
) -> list[MetricInfoBody]:
    """사용 가능한 평가 메트릭 카탈로그 — 평가기 탭·실행 폼이 공유."""
    metric_targets: dict[MetricType, list[str]] = {m: [] for m in MetricType}
    for target, metrics in TARGET_METRICS.items():
        for m in metrics:
            metric_targets[m].append(target)

    return [
        MetricInfoBody(
            key=m.value,
            name=_METRIC_DISPLAY[m][0],
            description=_METRIC_DISPLAY[m][1],
            target_types=metric_targets[m],
            requires_ground_truth=m in METRICS_REQUIRING_GROUND_TRUTH,
        )
        for m in MetricType
    ]


# ── 배치 평가 (A8) ───────────────────────────────────────────────────

@router.post("/batch", status_code=202, response_model=BatchEvalResponseBody)
async def create_batch_evaluation(
    body: BatchEvalRequestBody,
    use_case=Depends(get_batch_eval_use_case),
    user: User = Depends(get_current_user),
) -> BatchEvalResponseBody:
    from src.application.ragas.schemas import BatchEvalRequest

    request_id = str(uuid.uuid4())
    request = BatchEvalRequest(
        target_type=body.target_type,
        metrics=body.metrics,
        testcases=body.testcases,
        testset_id=body.testset_id,
        top_k=body.top_k,
        sample_ratio=body.sample_ratio,
        llm_model=body.llm_model,
        agent_id=body.agent_id,
        collection_name=body.collection_name,
    )
    try:
        response = await use_case.execute(
            request,
            request_id,
            user_id=str(user.id),
            scope_user_id=_scope(user),
        )
    except ValueError as e:
        _raise_eval_error(e)
    return BatchEvalResponseBody(
        run_id=response.run_id,
        status=response.status,
        total_cases=response.total_cases,
        message=response.message,
    )


@router.get("/runs", response_model=PaginatedResponse)
async def list_evaluation_runs(
    target_type: str | None = Query(None),
    eval_type: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    use_case=Depends(get_eval_result_use_case),
    user: User = Depends(get_current_user),
) -> PaginatedResponse:
    request_id = str(uuid.uuid4())
    items, total = await use_case.list_runs(
        target_type, eval_type, limit, offset, request_id,
        scope_user_id=_scope(user),
    )
    return PaginatedResponse(
        items=[_to_run_body(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/runs/{run_id}", response_model=EvalRunDetailBody)
async def get_evaluation_run(
    run_id: str,
    use_case=Depends(get_eval_result_use_case),
    user: User = Depends(get_current_user),
) -> EvalRunDetailBody:
    request_id = str(uuid.uuid4())
    detail = await use_case.get_run_detail(
        run_id, request_id, scope_user_id=_scope(user)
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return _to_run_body(detail)


@router.get("/runs/{run_id}/results", response_model=PaginatedResponse)
async def get_evaluation_results(
    run_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    use_case=Depends(get_eval_result_use_case),
    user: User = Depends(get_current_user),
) -> PaginatedResponse:
    request_id = str(uuid.uuid4())
    items, total = await use_case.get_results(
        run_id, limit, offset, request_id, scope_user_id=_scope(user)
    )
    return PaginatedResponse(
        items=[_to_result_body(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete("/runs/{run_id}", status_code=204)
async def delete_evaluation_run(
    run_id: str,
    use_case=Depends(get_eval_result_use_case),
    user: User = Depends(get_current_user),
) -> None:
    request_id = str(uuid.uuid4())
    deleted = await use_case.delete_run(
        run_id, request_id, scope_user_id=_scope(user)
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Evaluation run not found")


# ── 실시간 평가 ──────────────────────────────────────────────────────

@router.post("/realtime/evaluate", response_model=RealtimeEvalResponseBody)
async def realtime_evaluate(
    body: RealtimeEvalRequestBody,
    use_case=Depends(get_realtime_eval_use_case),
    user: User = Depends(get_current_user),
) -> RealtimeEvalResponseBody:
    from src.application.ragas.schemas import RealtimeEvalRequest

    request_id = str(uuid.uuid4())
    request = RealtimeEvalRequest(
        question=body.question,
        answer=body.answer,
        contexts=body.contexts,
        ground_truth=body.ground_truth,
        metrics=body.metrics,
        target_type=body.target_type,
    )
    response = await use_case.execute(request, request_id, user_id=str(user.id))
    return RealtimeEvalResponseBody(
        result_id=response.result_id,
        scores=response.scores,
    )


@router.get("/realtime/recent", response_model=list[EvalResultItemBody])
async def get_recent_realtime(
    limit: int = Query(20, ge=1, le=100),
    use_case=Depends(get_eval_result_use_case),
    user: User = Depends(get_current_user),
) -> list[EvalResultItemBody]:
    request_id = str(uuid.uuid4())
    items = await use_case.get_recent_realtime(
        limit, request_id, scope_user_id=_scope(user)
    )
    return [_to_result_body(i) for i in items]


# ── 테스트셋 관리 (A1~A6) ────────────────────────────────────────────

@router.post("/testsets", status_code=201, response_model=TestsetResponseBody)
async def create_testset(
    body: TestsetUploadRequestBody,
    use_case=Depends(get_testset_use_case),
    user: User = Depends(get_current_user),
) -> TestsetResponseBody:
    from src.application.ragas.schemas import TestsetUploadRequest

    request_id = str(uuid.uuid4())
    request = TestsetUploadRequest(
        name=body.name,
        description=body.description,
        cases=body.cases,
    )
    response = await use_case.create(request, request_id, user_id=str(user.id))
    return _to_testset_body(response)


@router.post(
    "/testsets/upload", status_code=201, response_model=TestsetResponseBody
)
async def upload_testset(
    file: UploadFile = File(...),
    name: str = Form(..., max_length=200),
    description: str = Form(""),
    use_case=Depends(get_testset_use_case),
    user: User = Depends(get_current_user),
) -> TestsetResponseBody:
    """CSV/XLSX 업로드로 테스트셋 생성 — 파싱 실패는 422."""
    request_id = str(uuid.uuid4())
    file_bytes = await file.read()
    try:
        response = await use_case.create_from_file(
            name=name,
            description=description,
            file_bytes=file_bytes,
            filename=file.filename or "",
            request_id=request_id,
            user_id=str(user.id),
        )
    except ValueError as e:
        _raise_eval_error(e)
    return _to_testset_body(response)


@router.post("/testsets/generate", response_model=GeneratedDraftResponseBody)
async def generate_testset_draft(
    file: UploadFile = File(...),
    max_pairs: int = Form(10, ge=1, le=50),
    use_case=Depends(get_testset_generate_use_case),
    user: User = Depends(get_current_user),
) -> GeneratedDraftResponseBody:
    """PDF/DOCX → LLM QA 쌍 초안 생성 — 저장하지 않는다(사용자 검토 후 create)."""
    request_id = str(uuid.uuid4())
    file_bytes = await file.read()
    try:
        draft = await use_case.execute(
            file_bytes, file.filename or "", max_pairs, request_id
        )
    except ValueError as e:
        _raise_eval_error(e)
    except Exception as e:  # LLM 호출 실패 등 — 원인 표면화 (은닉 금지)
        raise HTTPException(
            status_code=502, detail=f"QA 초안 생성에 실패했습니다: {e}"
        ) from e
    return GeneratedDraftResponseBody(
        source_filename=draft.source_filename,
        items=draft.items,
    )


@router.get("/testsets", response_model=PaginatedResponse)
async def list_testsets(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    use_case=Depends(get_testset_use_case),
    user: User = Depends(get_current_user),
) -> PaginatedResponse:
    request_id = str(uuid.uuid4())
    items, total = await use_case.list_all(
        limit, offset, request_id, scope_user_id=_scope(user)
    )
    return PaginatedResponse(
        items=[_to_testset_body(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/testsets/{testset_id}", response_model=TestsetDetailResponseBody)
async def get_testset(
    testset_id: str,
    use_case=Depends(get_testset_use_case),
    user: User = Depends(get_current_user),
) -> TestsetDetailResponseBody:
    request_id = str(uuid.uuid4())
    detail = await use_case.get_detail(
        testset_id, request_id, scope_user_id=_scope(user)
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="Testset not found")
    return TestsetDetailResponseBody(
        id=detail.id,
        name=detail.name,
        description=detail.description,
        case_count=detail.case_count,
        created_at=detail.created_at,
        user_id=detail.user_id,
        cases=detail.cases,
    )


@router.delete("/testsets/{testset_id}", status_code=204)
async def delete_testset(
    testset_id: str,
    use_case=Depends(get_testset_use_case),
    user: User = Depends(get_current_user),
) -> None:
    request_id = str(uuid.uuid4())
    deleted = await use_case.delete(
        testset_id, request_id, scope_user_id=_scope(user)
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Testset not found")


# ── 모델 스윕 (agent-model-benchmark §4.1) ───────────────────────────
#
# 검증 실패는 _raise_eval_error가 422로 매핑한다. Design §4.2는 400으로 적었으나
# 이 라우터의 기존 선례(배치 평가·테스트셋)를 따라 422로 통일한다.

@router.post("/sweeps/estimate", response_model=SweepEstimateResponse)
async def estimate_sweep(
    body: SweepEstimateRequest,
    use_case=Depends(get_estimate_sweep_use_case),
    user: User = Depends(get_current_user),
) -> SweepEstimateResponse:
    """실행 전 예상 비용·소요시간. 부수효과 없음 (FR-05)."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(body, request_id)
    except ValueError as e:
        _raise_eval_error(e)


@router.post("/sweeps", status_code=202, response_model=CreateSweepResponse)
async def create_sweep(
    body: CreateSweepRequest,
    use_case=Depends(get_create_sweep_use_case),
    user: User = Depends(get_current_user),
) -> CreateSweepResponse:
    """스윕 생성 + 순차 실행 시작 (202 Accepted)."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(body, request_id, user_id=str(user.id))
    except ValueError as e:
        _raise_eval_error(e)


@router.get("/sweeps", response_model=PaginatedResponse)
async def list_sweeps(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    use_case=Depends(get_list_sweeps_use_case),
    user: User = Depends(get_current_user),
) -> PaginatedResponse:
    request_id = str(uuid.uuid4())
    items, total = await use_case.execute(
        limit, offset, request_id, scope_user_id=_scope(user)
    )
    return PaginatedResponse(
        items=[i.model_dump() for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/sweeps/{sweep_id}", response_model=SweepDetailResponse)
async def get_sweep(
    sweep_id: str,
    use_case=Depends(get_sweep_detail_use_case),
    user: User = Depends(get_current_user),
) -> SweepDetailResponse:
    """스윕 상세 + 모델별 4축 집계 (FR-09)."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(
            sweep_id, request_id, scope_user_id=_scope(user)
        )
    except ValueError as e:
        _raise_eval_error(e)


@router.delete("/sweeps/{sweep_id}", status_code=204)
async def delete_sweep(
    sweep_id: str,
    use_case=Depends(get_delete_sweep_use_case),
    user: User = Depends(get_current_user),
) -> None:
    request_id = str(uuid.uuid4())
    try:
        await use_case.execute(sweep_id, request_id, scope_user_id=_scope(user))
    except ValueError as e:
        _raise_eval_error(e)
