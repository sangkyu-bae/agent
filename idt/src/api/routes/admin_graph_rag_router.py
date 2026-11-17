"""Admin graph-rag router: /api/v1/admin/graph-rag/*.

Design Ref: graph-rag-foundation §4.1·§6.1 — 라우터는 변환·오류 매핑만 한다.
module-2 설정·단계·상태, module-3 추출 잡. 엔티티·검색 테스트·검토는 module-4·5.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.application.graph_rag.admin.health_use_case import GraphHealthUseCase
from src.application.graph_rag.admin.jobs_use_case import (
    DocumentNotFoundError,
    ExtractionJobsUseCase,
    GraphJobBusyError,
    GraphModelMissingError,
    GraphUnsupportedDocumentError,
)
from src.application.graph_rag.admin.settings_use_case import (
    GraphRagSettingsUpdate,
    GraphRagSettingsUseCase,
)
from src.application.graph_rag.admin.stage_use_case import ChangeStageUseCase
from src.domain.auth.entities import User
from src.domain.graph_rag.exceptions import (
    GraphBackendUnavailableError,
    GraphRagError,
    GraphStageEvalRequiredError,
    GraphStageOffError,
)
from src.domain.graph_rag.extraction import JobMode
from src.domain.graph_rag.value_objects import RolloutStage
from src.interfaces.dependencies.auth import require_role
from src.interfaces.schemas.graph_rag import (
    ExtractAcceptedResponse,
    ExtractionJobResponse,
    ExtractRequest,
    GraphHealthResponse,
    GraphRagSettingsRequest,
    GraphRagSettingsResponse,
    KbDocumentJobItem,
    KbDocumentJobsResponse,
    StageChangeItem,
    StageChangeRequest,
    StageHistoryResponse,
)

router = APIRouter(prefix="/api/v1/admin/graph-rag", tags=["admin-graph-rag"])

_HISTORY_LIMIT = 50


def get_graph_rag_settings_use_case() -> GraphRagSettingsUseCase:
    raise NotImplementedError("GraphRagSettingsUseCase not wired (wire_graph_rag)")


def get_change_stage_use_case() -> ChangeStageUseCase:
    raise NotImplementedError("ChangeStageUseCase not wired (wire_graph_rag)")


def get_graph_health_use_case() -> GraphHealthUseCase:
    raise NotImplementedError("GraphHealthUseCase not wired (wire_graph_rag)")


def get_extraction_jobs_use_case() -> ExtractionJobsUseCase:
    raise NotImplementedError("ExtractionJobsUseCase not wired (wire_graph_rag)")


# Design §6.1 오류 코드 → HTTP 상태
_ERROR_STATUS: dict[type[GraphRagError], int] = {
    GraphStageOffError: status.HTTP_409_CONFLICT,
    GraphJobBusyError: status.HTTP_409_CONFLICT,
    GraphModelMissingError: 422,
    GraphUnsupportedDocumentError: 422,
    DocumentNotFoundError: status.HTTP_404_NOT_FOUND,
    GraphBackendUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
}


def _error(code: str, message: str, http_status: int) -> HTTPException:
    return HTTPException(
        status_code=http_status, detail={"code": code, "message": message}
    )


def _request_id(user: User) -> str:
    return f"admin-graph-{user.id}"


@router.get("/settings", response_model=GraphRagSettingsResponse)
async def get_settings(
    current_user: User = Depends(require_role("admin")),
    use_case: GraphRagSettingsUseCase = Depends(get_graph_rag_settings_use_case),
) -> GraphRagSettingsResponse:
    return GraphRagSettingsResponse.from_domain(
        await use_case.get(_request_id(current_user))
    )


@router.put("/settings", response_model=GraphRagSettingsResponse)
async def put_settings(
    body: GraphRagSettingsRequest,
    current_user: User = Depends(require_role("admin")),
    use_case: GraphRagSettingsUseCase = Depends(get_graph_rag_settings_use_case),
) -> GraphRagSettingsResponse:
    fields = body.model_dump()
    fields["entity_types"] = tuple(body.entity_types)
    fields["relation_types"] = tuple(body.relation_types)
    try:
        saved = await use_case.update(
            GraphRagSettingsUpdate(**fields), _request_id(current_user)
        )
    except ValueError as e:
        raise _error("GRAPH_SETTINGS_INVALID", str(e), 422) from e
    return GraphRagSettingsResponse.from_domain(saved)


@router.post("/stage", response_model=GraphRagSettingsResponse)
async def change_stage(
    body: StageChangeRequest,
    current_user: User = Depends(require_role("admin")),
    use_case: ChangeStageUseCase = Depends(get_change_stage_use_case),
) -> GraphRagSettingsResponse:
    try:
        target = RolloutStage.from_string(body.to_stage)
    except ValueError as e:
        raise _error("GRAPH_SETTINGS_INVALID", str(e), 422) from e
    try:
        saved = await use_case.change(
            target,
            actor_id=str(current_user.id),
            request_id=_request_id(current_user),
            eval_baseline_run_id=body.eval_baseline_run_id,
            eval_graph_run_id=body.eval_graph_run_id,
            force_reason=body.force_reason,
        )
    except GraphStageEvalRequiredError as e:
        raise _error(e.code, str(e), status.HTTP_409_CONFLICT) from e
    return GraphRagSettingsResponse.from_domain(saved)


@router.get("/stage-history", response_model=StageHistoryResponse)
async def stage_history(
    current_user: User = Depends(require_role("admin")),
    use_case: ChangeStageUseCase = Depends(get_change_stage_use_case),
) -> StageHistoryResponse:
    items = await use_case.history(_HISTORY_LIMIT, _request_id(current_user))
    return StageHistoryResponse(items=[StageChangeItem.from_domain(c) for c in items])


@router.get("/health", response_model=GraphHealthResponse)
async def health(
    current_user: User = Depends(require_role("admin")),
    use_case: GraphHealthUseCase = Depends(get_graph_health_use_case),
) -> GraphHealthResponse:
    return GraphHealthResponse.from_domain(await use_case.execute())


# ── module-3: 추출 잡 ──────────────────────────────────────────────────────


@router.get("/kbs/{kb_id}/documents", response_model=KbDocumentJobsResponse)
async def kb_documents(
    kb_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(require_role("admin")),
    use_case: ExtractionJobsUseCase = Depends(get_extraction_jobs_use_case),
) -> KbDocumentJobsResponse:
    rows, total = await use_case.list_kb_documents(
        kb_id, _request_id(current_user), limit=limit, offset=offset
    )
    return KbDocumentJobsResponse(
        total=total,
        items=[
            KbDocumentJobItem(
                document_id=r.document_id,
                filename=r.filename,
                chunk_count=r.chunk_count,
                job=ExtractionJobResponse.from_domain(r.job) if r.job else None,
            )
            for r in rows
        ],
    )


@router.post(
    "/documents/{document_id}/extract",
    response_model=ExtractAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def extract_document(
    document_id: str,
    body: ExtractRequest,
    current_user: User = Depends(require_role("admin")),
    use_case: ExtractionJobsUseCase = Depends(get_extraction_jobs_use_case),
) -> ExtractAcceptedResponse:
    try:
        job = await use_case.trigger(
            document_id,
            JobMode(body.mode),
            actor_id=str(current_user.id),
            request_id=_request_id(current_user),
        )
    except GraphRagError as e:
        http_status = _ERROR_STATUS.get(type(e))
        if http_status is None:
            raise
        raise _error(e.code, str(e), http_status) from e
    return ExtractAcceptedResponse(job_id=job.id, status=job.status.value)


@router.get("/jobs/{job_id}", response_model=ExtractionJobResponse)
async def job_detail(
    job_id: str,
    current_user: User = Depends(require_role("admin")),
    use_case: ExtractionJobsUseCase = Depends(get_extraction_jobs_use_case),
) -> ExtractionJobResponse:
    job = await use_case.get(job_id, _request_id(current_user))
    if job is None:
        raise _error("JOB_NOT_FOUND", f"job not found: {job_id}", 404)
    return ExtractionJobResponse.from_domain(job)
