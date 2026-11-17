"""Admin graph-rag router: /api/v1/admin/graph-rag/* (module-2: 설정·단계·상태).

Design Ref: graph-rag-foundation §4.1·§6.1 — 라우터는 변환·오류 매핑만 한다.
추출·엔티티·검색 테스트·검토 API 는 module-3~5 에서 이 라우터에 추가된다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.graph_rag.admin.health_use_case import GraphHealthUseCase
from src.application.graph_rag.admin.settings_use_case import (
    GraphRagSettingsUpdate,
    GraphRagSettingsUseCase,
)
from src.application.graph_rag.admin.stage_use_case import ChangeStageUseCase
from src.domain.auth.entities import User
from src.domain.graph_rag.exceptions import GraphStageEvalRequiredError
from src.domain.graph_rag.value_objects import RolloutStage
from src.interfaces.dependencies.auth import require_role
from src.interfaces.schemas.graph_rag import (
    GraphHealthResponse,
    GraphRagSettingsRequest,
    GraphRagSettingsResponse,
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
