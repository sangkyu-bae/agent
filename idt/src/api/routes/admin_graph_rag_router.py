"""Admin graph-rag router: /api/v1/admin/graph-rag/*.

Design Ref: graph-rag-foundation §4.1·§6.1 — 라우터는 변환·오류 매핑만 한다.
module-2 설정·단계·상태, module-3 추출 잡, module-4 검토 큐, module-4b 주제 목록,
module-5b 엔티티·검색 테스트·정합성 점검.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.application.graph_rag.admin.health_use_case import GraphHealthUseCase
from src.application.graph_rag.admin.inspect_use_case import InspectUseCase
from src.application.graph_rag.admin.jobs_use_case import (
    DocumentNotFoundError,
    ExtractionJobsUseCase,
    GraphJobBusyError,
    GraphModelMissingError,
    GraphUnsupportedDocumentError,
)
from src.application.graph_rag.admin.review_use_case import (
    GraphReviewAlreadyDoneError,
    GraphReviewNotFoundError,
    GraphReviewTargetInvalidError,
    ReviewUseCase,
)
from src.application.graph_rag.admin.search_test_use_case import SearchTestUseCase
from src.application.graph_rag.admin.settings_use_case import (
    GraphRagSettingsUpdate,
    GraphRagSettingsUseCase,
)
from src.application.graph_rag.admin.stage_use_case import ChangeStageUseCase
from src.application.graph_rag.admin.topics_use_case import TopicsUseCase
from src.domain.auth.entities import User
from src.domain.graph_rag.exceptions import (
    GraphBackendUnavailableError,
    GraphRagError,
    GraphStageEvalRequiredError,
    GraphStageOffError,
    GraphTopicDuplicateError,
    GraphTopicInvalidError,
    GraphTopicNotFoundError,
)
from src.domain.graph_rag.extraction import JobMode
from src.domain.graph_rag.resolution import ReviewStatus
from src.domain.graph_rag.value_objects import RolloutStage
from src.interfaces.dependencies.auth import require_role
from src.interfaces.schemas.graph_rag import (
    EntityDetailResponse,
    EntityItem,
    EntityListResponse,
    ExtractAcceptedResponse,
    ExtractionJobResponse,
    ExtractRequest,
    GraphHealthResponse,
    GraphRagSettingsRequest,
    GraphRagSettingsResponse,
    IntegrityResponse,
    KbDocumentJobItem,
    KbDocumentJobsResponse,
    ReviewApproveRequest,
    ReviewItem,
    ReviewListResponse,
    ReviewRejectRequest,
    ReviewRejectResponse,
    SearchTestRequest,
    SearchTestResponse,
    StageChangeItem,
    StageChangeRequest,
    StageHistoryResponse,
    TopicCreateRequest,
    TopicItem,
    TopicListResponse,
    TopicUpdateRequest,
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


def get_review_use_case() -> ReviewUseCase:
    raise NotImplementedError("ReviewUseCase not wired (wire_graph_rag)")


def get_topics_use_case() -> TopicsUseCase:
    raise NotImplementedError("TopicsUseCase not wired (wire_graph_rag)")


def get_inspect_use_case() -> InspectUseCase:
    raise NotImplementedError("InspectUseCase not wired (wire_graph_rag)")


def get_search_test_use_case() -> SearchTestUseCase:
    raise NotImplementedError("SearchTestUseCase not wired (wire_graph_rag)")


# Design §6.1 오류 코드 → HTTP 상태
_ERROR_STATUS: dict[type[GraphRagError], int] = {
    GraphStageOffError: status.HTTP_409_CONFLICT,
    GraphJobBusyError: status.HTTP_409_CONFLICT,
    GraphModelMissingError: 422,
    GraphUnsupportedDocumentError: 422,
    DocumentNotFoundError: status.HTTP_404_NOT_FOUND,
    GraphBackendUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
    GraphReviewNotFoundError: status.HTTP_404_NOT_FOUND,
    GraphReviewAlreadyDoneError: status.HTTP_409_CONFLICT,
    GraphReviewTargetInvalidError: 422,
    GraphTopicInvalidError: 422,
    GraphTopicNotFoundError: status.HTTP_404_NOT_FOUND,
    GraphTopicDuplicateError: status.HTTP_409_CONFLICT,
}


def _mapped(e: GraphRagError) -> HTTPException:
    http_status = _ERROR_STATUS.get(type(e))
    if http_status is None:
        raise e
    return _error(e.code, str(e), http_status)


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


# ── module-4: 검토 큐 ──────────────────────────────────────────────────────


@router.get("/review", response_model=ReviewListResponse)
async def review_list(
    status_: str = Query(default="pending", alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(require_role("admin")),
    use_case: ReviewUseCase = Depends(get_review_use_case),
) -> ReviewListResponse:
    try:
        review_status = ReviewStatus(status_)
    except ValueError as e:
        raise _error("GRAPH_SETTINGS_INVALID", str(e), 422) from e
    items, total = await use_case.list(
        review_status, limit, offset, _request_id(current_user)
    )
    return ReviewListResponse(
        items=[ReviewItem.from_domain(d) for d in items], total=total
    )


@router.post("/review/{decision_id}/approve", status_code=status.HTTP_204_NO_CONTENT)
async def review_approve(
    decision_id: str,
    body: ReviewApproveRequest,
    current_user: User = Depends(require_role("admin")),
    use_case: ReviewUseCase = Depends(get_review_use_case),
) -> None:
    try:
        await use_case.approve(
            decision_id,
            reviewer=str(current_user.id),
            note=body.note,
            request_id=_request_id(current_user),
        )
    except GraphRagError as e:
        raise _mapped(e) from e


@router.post("/review/{decision_id}/reject", response_model=ReviewRejectResponse)
async def review_reject(
    decision_id: str,
    body: ReviewRejectRequest,
    current_user: User = Depends(require_role("admin")),
    use_case: ReviewUseCase = Depends(get_review_use_case),
) -> ReviewRejectResponse:
    try:
        entity_id = await use_case.reject(
            decision_id,
            reviewer=str(current_user.id),
            note=body.note,
            target_entity_id=body.target_entity_id,
            request_id=_request_id(current_user),
        )
    except GraphRagError as e:
        raise _mapped(e) from e
    return ReviewRejectResponse(entity_id=entity_id)


# ── module-4b: 주제 목록 (Design §11.9) ────────────────────────────────────


@router.get("/topics", response_model=TopicListResponse)
async def topic_list(
    include_retired: bool = Query(default=False),
    current_user: User = Depends(require_role("admin")),
    use_case: TopicsUseCase = Depends(get_topics_use_case),
) -> TopicListResponse:
    rows = await use_case.list(
        include_retired=include_retired, request_id=_request_id(current_user)
    )
    return TopicListResponse(items=[TopicItem.from_domain(t, n) for t, n in rows])


@router.post("/topics", response_model=TopicItem, status_code=status.HTTP_201_CREATED)
async def topic_create(
    body: TopicCreateRequest,
    current_user: User = Depends(require_role("admin")),
    use_case: TopicsUseCase = Depends(get_topics_use_case),
) -> TopicItem:
    try:
        topic = await use_case.create(
            name=body.name,
            level=body.level,
            parent_id=body.parent_id,
            description=body.description,
            actor=str(current_user.id),
            request_id=_request_id(current_user),
        )
    except GraphRagError as e:
        raise _mapped(e) from e
    return TopicItem.from_domain(topic)


@router.patch("/topics/{topic_id}", response_model=TopicItem)
async def topic_update(
    topic_id: str,
    body: TopicUpdateRequest,
    current_user: User = Depends(require_role("admin")),
    use_case: TopicsUseCase = Depends(get_topics_use_case),
) -> TopicItem:
    try:
        topic = await use_case.update(
            topic_id,
            name=body.name,
            description=body.description,
            status=body.status,
            request_id=_request_id(current_user),
        )
    except GraphRagError as e:
        raise _mapped(e) from e
    return TopicItem.from_domain(topic)


# ── module-5b: 엔티티·검색 테스트·정합성 (Design §4.1·§4.2) ─────────────────


@router.get("/entities", response_model=EntityListResponse)
async def entity_list(
    q: str | None = Query(default=None, max_length=100),
    type_: str | None = Query(default=None, alias="type", max_length=32),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_role("admin")),
    use_case: InspectUseCase = Depends(get_inspect_use_case),
) -> EntityListResponse:
    try:
        items, total = await use_case.entities(
            query=q, type_=type_, page=page, size=size
        )
    except GraphRagError as e:
        raise _mapped(e) from e
    return EntityListResponse(
        items=[EntityItem.from_domain(e) for e in items],
        total=total,
        page=page,
        size=size,
    )


@router.get("/entities/{entity_id}", response_model=EntityDetailResponse)
async def entity_detail(
    entity_id: str,
    current_user: User = Depends(require_role("admin")),
    use_case: InspectUseCase = Depends(get_inspect_use_case),
) -> EntityDetailResponse:
    try:
        detail = await use_case.entity(entity_id, _request_id(current_user))
    except GraphRagError as e:
        raise _mapped(e) from e
    if detail is None:
        raise _error(
            "GRAPH_ENTITY_NOT_FOUND",
            f"entity not found: {entity_id}",
            status.HTTP_404_NOT_FOUND,
        )
    return EntityDetailResponse.from_domain(detail)


@router.post("/search-test", response_model=SearchTestResponse)
async def search_test(
    body: SearchTestRequest,
    current_user: User = Depends(require_role("admin")),
    use_case: SearchTestUseCase = Depends(get_search_test_use_case),
) -> SearchTestResponse:
    try:
        result = await use_case.run(
            query=body.query,
            kb_id=body.kb_id,
            collection_name=body.collection_name,
            top_k=body.top_k,
            max_hops=body.max_hops,
            request_id=_request_id(current_user),
        )
    except GraphRagError as e:
        raise _mapped(e) from e
    return SearchTestResponse.from_result(result)


@router.get("/integrity", response_model=IntegrityResponse)
async def integrity(
    kb_id: str | None = Query(default=None, max_length=36),
    sample: int = Query(default=500, ge=1, le=2000),
    current_user: User = Depends(require_role("admin")),
    use_case: InspectUseCase = Depends(get_inspect_use_case),
) -> IntegrityResponse:
    try:
        report = await use_case.integrity(
            kb_id=kb_id, sample=sample, request_id=_request_id(current_user)
        )
    except GraphRagError as e:
        raise _mapped(e) from e
    return IntegrityResponse.from_domain(report)
