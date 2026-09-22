"""승인 게이트 라우터 (/api/v1/approvals).

Design Ref: §4 (API), §6.1 (에러 매핑).

라우터는 비즈니스 로직을 갖지 않는다 — 권한·전이·멱등은 전부 UseCase 와
도메인 Policy 가 판정하고, 여기서는 오류를 HTTP 로 번역만 한다.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from src.application.approval.errors import ApprovalError
from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import get_current_user
from src.interfaces.schemas.approval import (
    ApprovalGateSettingsRequest,
    ApprovalGateSettingsResponse,
    ApprovalDecisionResponse,
    ApprovalDetailResponse,
    ApprovalListResponse,
    ApprovalTickResponse,
    RejectApprovalRequest,
    to_detail,
    to_item,
)

router = APIRouter(prefix="/api/v1/approvals", tags=["Approval Gate"])
internal_router = APIRouter(
    prefix="/api/v1/internal/approvals", tags=["Approval Gate (internal)"]
)
# approval-gate Check G3: 에이전트별 게이트 설정 입구
agent_gate_router = APIRouter(prefix="/api/v1/agents", tags=["Approval Gate"])


# ── DI 플레이스홀더 (main.py에서 override) ──────────────────────────

def get_list_approvals_use_case():
    raise NotImplementedError


def get_decide_approval_use_case():
    raise NotImplementedError


def get_execute_due_approvals_use_case():
    raise NotImplementedError


def get_gate_settings_use_case():
    raise NotImplementedError


def verify_scheduler_token():
    """internal tick 인증 — main.py 가 스케줄러 토큰 검증으로 override 한다."""
    raise NotImplementedError


def _http(error: ApprovalError) -> HTTPException:
    """Design §6.1 — 오류가 소유한 code/status 를 그대로 옮긴다.

    라우터가 상태 코드를 자체 판단하지 않는 이유: 같은 오류를 두 곳에서
    다르게 번역하면 프론트가 분기를 두 벌 갖게 된다.
    """
    return HTTPException(
        status_code=error.http_status,
        detail={"code": error.code, "message": str(error) or error.code},
    )


@router.get("", response_model=ApprovalListResponse)
async def list_approvals(
    status: str | None = Query(
        None, description="쉼표 구분. 기본 pending,scheduled"
    ),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_list_approvals_use_case),
):
    request_id = str(uuid.uuid4())
    kwargs = {}
    if status:
        kwargs["statuses"] = tuple(
            s.strip() for s in status.split(",") if s.strip()
        )
    result = await use_case.list(
        user_id=str(current_user.id), request_id=request_id,
        page=page, size=size, **kwargs,
    )
    return ApprovalListResponse(
        data=[to_item(a, result.agent_names.get(a.agent_id)) for a in result.items],
        pagination={"total": result.total, "page": page, "size": size},
    )


@router.get("/{approval_id}", response_model=ApprovalDetailResponse)
async def get_approval(
    approval_id: str,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_decide_approval_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        approval, agent_name = await use_case.get(
            approval_id, user_id=str(current_user.id), request_id=request_id
        )
    except ApprovalError as e:
        raise _http(e) from e
    return to_detail(approval, agent_name)


@router.post("/{approval_id}/approve", response_model=ApprovalDecisionResponse)
async def approve(
    approval_id: str,
    execute_only: bool = Query(
        False, description="정의 변경 시 재개를 포기하고 집행만 (FR-14)"
    ),
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_decide_approval_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        approval = await use_case.approve(
            approval_id, user_id=str(current_user.id),
            request_id=request_id, execute_only=execute_only,
        )
    except ApprovalError as e:
        raise _http(e) from e
    return ApprovalDecisionResponse(
        id=approval.id, status=approval.status,
        execute_after=approval.execute_after,
        message=_approve_message(approval),
    )


@router.post("/{approval_id}/reject", response_model=ApprovalDecisionResponse)
async def reject(
    approval_id: str,
    body: RejectApprovalRequest,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_decide_approval_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        approval = await use_case.reject(
            approval_id, user_id=str(current_user.id),
            reason=body.reason, request_id=request_id,
        )
    except ApprovalError as e:
        raise _http(e) from e
    return ApprovalDecisionResponse(
        id=approval.id, status=approval.status, message="거절 처리되었습니다."
    )


@router.post("/{approval_id}/seen", status_code=204)
async def mark_seen(
    approval_id: str,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_list_approvals_use_case),
):
    await use_case.mark_seen(
        approval_id, user_id=str(current_user.id), request_id=str(uuid.uuid4())
    )


@internal_router.post(
    "/tick",
    response_model=ApprovalTickResponse,
    dependencies=[Depends(verify_scheduler_token)],
)
async def tick(use_case=Depends(get_execute_due_approvals_use_case)):
    """예약 집행 tick — 승인 시각과 분리된 '정시' 를 담당한다 (Design §2.1)."""
    result = await use_case.run(str(uuid.uuid4()))
    return ApprovalTickResponse(
        claimed_count=result.claimed_count,
        executed_count=result.executed_count,
        failed_count=result.failed_count,
        expired_count=result.expired_count,
    )


def _approve_message(approval) -> str:
    # Check G12: 서버는 사용자 벽시계를 모른다. 시각은 execute_after(UTC 명시)로
    # 내려주고, 사람이 읽는 시각 포맷은 로캘을 아는 프론트가 만든다.
    if approval.status == "scheduled":
        return "승인되었습니다. 예약된 시각에 집행됩니다."
    if approval.status == "failed":
        return f"집행에 실패했습니다: {approval.error_message or '사유 미상'}"
    return "집행되었습니다."


@agent_gate_router.get(
    "/{agent_id}/approval-gate", response_model=ApprovalGateSettingsResponse
)
async def get_gate_settings(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_gate_settings_use_case),
):
    try:
        return await use_case.get(
            agent_id, user_id=str(current_user.id), request_id=str(uuid.uuid4())
        )
    except ApprovalError as e:
        raise _http(e) from e


@agent_gate_router.put(
    "/{agent_id}/approval-gate", response_model=ApprovalGateSettingsResponse
)
async def put_gate_settings(
    agent_id: str,
    body: ApprovalGateSettingsRequest,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_gate_settings_use_case),
):
    """에이전트별 게이트 설정 저장 — 검증은 MiddlewareConfigPolicy (Check G3)."""
    from src.application.approval.gate_settings_use_case import (
        GateUnavailableError,
    )

    try:
        return await use_case.put(
            agent_id, user_id=str(current_user.id),
            config=body.to_config(), request_id=str(uuid.uuid4()),
        )
    except ApprovalError as e:
        raise _http(e) from e
    except GateUnavailableError as e:
        raise HTTPException(
            status_code=409, detail={"code": e.code, "message": str(e)}
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "APPROVAL_GATE_INVALID_CONFIG", "message": str(e)},
        ) from e
