"""Agent Schedule Router: 에이전트 스케줄 CRUD + 외부 트리거 API.

Design: docs/02-design/features/agent-schedule.design.md §6.1
- CRUD: JWT(get_current_user), 스케줄/에이전트 소유자만
- 트리거: X-Scheduler-Token 헤더 == settings.scheduler_trigger_token
  (빈 값 = 기능 비활성 503, 불일치 401)
"""
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from src.application.agent_schedule.schemas import (
    CreateScheduleRequest,
    ScheduleResponse,
    ScheduleRunResponse,
    ToggleScheduleRequest,
    TriggerResponse,
    TriggerStatusResponse,
    UpdateScheduleRequest,
)
from src.config import settings
from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import get_current_user

router = APIRouter(prefix="/api/v1/agents", tags=["Agent Schedule"])
trigger_router = APIRouter(
    prefix="/api/v1/internal/schedules", tags=["Agent Schedule (internal)"]
)


# ── DI 플레이스홀더 (main.py에서 override) ──────────────────────────

def get_create_schedule_use_case():
    raise NotImplementedError


def get_list_schedules_use_case():
    raise NotImplementedError


def get_get_schedule_use_case():
    raise NotImplementedError


def get_update_schedule_use_case():
    raise NotImplementedError


def get_delete_schedule_use_case():
    raise NotImplementedError


def get_toggle_schedule_use_case():
    raise NotImplementedError


def get_list_schedule_runs_use_case():
    raise NotImplementedError


def get_trigger_due_schedules_use_case():
    raise NotImplementedError


# ── 공용 헬퍼 ─────────────────────────────────────────────────────

def _http_error(e: ValueError) -> HTTPException:
    msg = str(e)
    if "찾을 수 없" in msg:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


def verify_scheduler_token(
    x_scheduler_token: str | None = Header(default=None),
) -> None:
    if not settings.scheduler_trigger_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="스케줄 트리거가 비활성 상태입니다 (SCHEDULER_TRIGGER_TOKEN 미설정)",
        )
    if x_scheduler_token != settings.scheduler_trigger_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="스케줄러 토큰이 유효하지 않습니다",
        )


# ── CRUD 엔드포인트 ──────────────────────────────────────────────


@router.post(
    "/{agent_id}/schedules",
    response_model=ScheduleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_schedule(
    agent_id: str,
    body: CreateScheduleRequest,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_create_schedule_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(agent_id, current_user.id, body, request_id)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise _http_error(e)


@router.get("/{agent_id}/schedules", response_model=list[ScheduleResponse])
async def list_schedules(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_list_schedules_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(agent_id, current_user.id, request_id)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise _http_error(e)


@router.get(
    "/{agent_id}/schedules/{schedule_id}", response_model=ScheduleResponse
)
async def get_schedule(
    agent_id: str,
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_get_schedule_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(
            agent_id, schedule_id, current_user.id, request_id
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise _http_error(e)


@router.put(
    "/{agent_id}/schedules/{schedule_id}", response_model=ScheduleResponse
)
async def update_schedule(
    agent_id: str,
    schedule_id: str,
    body: UpdateScheduleRequest,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_update_schedule_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(
            agent_id, schedule_id, current_user.id, body, request_id
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise _http_error(e)


@router.delete(
    "/{agent_id}/schedules/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_schedule(
    agent_id: str,
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_delete_schedule_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        await use_case.execute(agent_id, schedule_id, current_user.id, request_id)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise _http_error(e)


@router.patch(
    "/{agent_id}/schedules/{schedule_id}/enabled",
    response_model=ScheduleResponse,
)
async def toggle_schedule(
    agent_id: str,
    schedule_id: str,
    body: ToggleScheduleRequest,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_toggle_schedule_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(
            agent_id, schedule_id, current_user.id, body.enabled, request_id
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise _http_error(e)


@router.get(
    "/{agent_id}/schedules/{schedule_id}/runs",
    response_model=list[ScheduleRunResponse],
)
async def list_schedule_runs(
    agent_id: str,
    schedule_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_list_schedule_runs_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(
            agent_id, schedule_id, current_user.id, limit, offset, request_id
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise _http_error(e)


# ── 외부 트리거 엔드포인트 (X-Scheduler-Token) ─────────────────────


@trigger_router.post(
    "/trigger",
    response_model=TriggerResponse,
    dependencies=[Depends(verify_scheduler_token)],
)
async def trigger_due_schedules(
    use_case=Depends(get_trigger_due_schedules_use_case),
):
    request_id = str(uuid.uuid4())
    return await use_case.execute(request_id)


@trigger_router.get(
    "/trigger/status",
    response_model=TriggerStatusResponse,
    dependencies=[Depends(verify_scheduler_token)],
)
async def trigger_status(
    use_case=Depends(get_trigger_due_schedules_use_case),
):
    return use_case.status()
