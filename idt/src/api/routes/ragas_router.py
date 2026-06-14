"""RAGAS 평가 REST API 엔드포인트."""
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

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


# ── Request/Response 스키마 ──────────────────────────────────────────

class BatchEvalRequestBody(BaseModel):
    target_type: str = Field(..., pattern="^(rag|agent|retrieval)$")
    metrics: list[str]
    testcases: list[dict[str, Any]]
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


# ── 배치 평가 ────────────────────────────────────────────────────────

@router.post("/batch", status_code=202, response_model=BatchEvalResponseBody)
async def create_batch_evaluation(
    body: BatchEvalRequestBody,
    background_tasks: BackgroundTasks,
    use_case=Depends(get_batch_eval_use_case),
) -> BatchEvalResponseBody:
    from src.application.ragas.schemas import BatchEvalRequest

    request_id = str(uuid.uuid4())
    request = BatchEvalRequest(
        target_type=body.target_type,
        metrics=body.metrics,
        testcases=body.testcases,
        top_k=body.top_k,
        sample_ratio=body.sample_ratio,
        llm_model=body.llm_model,
        agent_id=body.agent_id,
        collection_name=body.collection_name,
    )
    response = await use_case.execute(request, request_id)
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
) -> PaginatedResponse:
    request_id = str(uuid.uuid4())
    items, total = await use_case.list_runs(
        target_type, eval_type, limit, offset, request_id
    )
    return PaginatedResponse(
        items=[
            EvalRunDetailBody(
                id=i.id,
                eval_type=i.eval_type,
                target_type=i.target_type,
                status=i.status,
                total_cases=i.total_cases,
                created_at=i.created_at,
                completed_at=i.completed_at,
                summary=i.summary,
            )
            for i in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/runs/{run_id}", response_model=EvalRunDetailBody)
async def get_evaluation_run(
    run_id: str,
    use_case=Depends(get_eval_result_use_case),
) -> EvalRunDetailBody:
    request_id = str(uuid.uuid4())
    detail = await use_case.get_run_detail(run_id, request_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return EvalRunDetailBody(
        id=detail.id,
        eval_type=detail.eval_type,
        target_type=detail.target_type,
        status=detail.status,
        total_cases=detail.total_cases,
        created_at=detail.created_at,
        completed_at=detail.completed_at,
        summary=detail.summary,
    )


@router.get("/runs/{run_id}/results", response_model=PaginatedResponse)
async def get_evaluation_results(
    run_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    use_case=Depends(get_eval_result_use_case),
) -> PaginatedResponse:
    request_id = str(uuid.uuid4())
    items, total = await use_case.get_results(run_id, limit, offset, request_id)
    return PaginatedResponse(
        items=[
            EvalResultItemBody(
                id=i.id,
                question=i.question,
                answer=i.answer,
                ground_truth=i.ground_truth,
                contexts=i.contexts,
                scores=i.scores,
                created_at=i.created_at,
            )
            for i in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete("/runs/{run_id}", status_code=204)
async def delete_evaluation_run(
    run_id: str,
    use_case=Depends(get_eval_result_use_case),
) -> None:
    request_id = str(uuid.uuid4())
    deleted = await use_case.delete_run(run_id, request_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Evaluation run not found")


# ── 실시간 평가 ──────────────────────────────────────────────────────

@router.post("/realtime/evaluate", response_model=RealtimeEvalResponseBody)
async def realtime_evaluate(
    body: RealtimeEvalRequestBody,
    use_case=Depends(get_realtime_eval_use_case),
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
    response = await use_case.execute(request, request_id)
    return RealtimeEvalResponseBody(
        result_id=response.result_id,
        scores=response.scores,
    )


@router.get("/realtime/recent", response_model=list[EvalResultItemBody])
async def get_recent_realtime(
    limit: int = Query(20, ge=1, le=100),
    use_case=Depends(get_eval_result_use_case),
) -> list[EvalResultItemBody]:
    request_id = str(uuid.uuid4())
    items = await use_case.get_recent_realtime(limit, request_id)
    return [
        EvalResultItemBody(
            id=i.id,
            question=i.question,
            answer=i.answer,
            ground_truth=i.ground_truth,
            contexts=i.contexts,
            scores=i.scores,
            created_at=i.created_at,
        )
        for i in items
    ]


# ── 테스트셋 관리 ────────────────────────────────────────────────────

@router.post("/testsets", status_code=201, response_model=TestsetResponseBody)
async def create_testset(
    body: TestsetUploadRequestBody,
    use_case=Depends(get_testset_use_case),
) -> TestsetResponseBody:
    from src.application.ragas.schemas import TestsetUploadRequest

    request_id = str(uuid.uuid4())
    request = TestsetUploadRequest(
        name=body.name,
        description=body.description,
        cases=body.cases,
    )
    response = await use_case.create(request, request_id)
    return TestsetResponseBody(
        id=response.id,
        name=response.name,
        description=response.description,
        case_count=response.case_count,
        created_at=response.created_at,
    )


@router.get("/testsets", response_model=PaginatedResponse)
async def list_testsets(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    use_case=Depends(get_testset_use_case),
) -> PaginatedResponse:
    request_id = str(uuid.uuid4())
    items, total = await use_case.list_all(limit, offset, request_id)
    return PaginatedResponse(
        items=[
            TestsetResponseBody(
                id=i.id,
                name=i.name,
                description=i.description,
                case_count=i.case_count,
                created_at=i.created_at,
            )
            for i in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/testsets/{testset_id}", response_model=TestsetResponseBody)
async def get_testset(
    testset_id: str,
    use_case=Depends(get_testset_use_case),
) -> TestsetResponseBody:
    request_id = str(uuid.uuid4())
    detail = await use_case.get_detail(testset_id, request_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Testset not found")
    return TestsetResponseBody(
        id=detail.id,
        name=detail.name,
        description=detail.description,
        case_count=detail.case_count,
        created_at=detail.created_at,
    )


@router.delete("/testsets/{testset_id}", status_code=204)
async def delete_testset(
    testset_id: str,
    use_case=Depends(get_testset_use_case),
) -> None:
    request_id = str(uuid.uuid4())
    deleted = await use_case.delete(testset_id, request_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Testset not found")
