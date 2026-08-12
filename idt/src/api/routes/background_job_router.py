"""Background Job Router: 백그라운드 작업 등록·조회·확인 처리 API.

Design: docs/02-design/features/background-jobs.design.md §4-5
- 등록: POST /api/v1/agents/{agent_id}/jobs (202, 세션 중복 409)
- 조회·확인: /api/v1/jobs* — 전부 본인 소유만 (타인 404, 사유 비구분)
- D14: 리터럴 경로(/jobs/unseen-count, /jobs/seen-all)를
  /jobs/{job_id} 보다 먼저 선언한다 (wiki tree 선언 순서 계약 교훈).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.application.background_job.errors import (
    JobConflictError,
    JobNotFoundError,
)
from src.application.background_job.schemas import (
    EnqueueJobRequest,
    EnqueueJobResponse,
    JobResponse,
    MyScheduleRunResponse,
    SeenAllResponse,
    UnseenCountResponse,
)
from src.domain.agent_run.auth_context import AuthContext
from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import get_auth_context, get_current_user

router = APIRouter(prefix="/api/v1", tags=["Background Jobs"])


# ── DI 플레이스홀더 (main.py에서 override) ──────────────────────────

def get_enqueue_job_use_case():
    raise NotImplementedError


def get_list_jobs_use_case():
    raise NotImplementedError


def get_get_job_use_case():
    raise NotImplementedError


def get_count_unseen_use_case():
    raise NotImplementedError


def get_mark_seen_use_case():
    raise NotImplementedError


def get_mark_all_seen_use_case():
    raise NotImplementedError


def get_list_my_schedule_runs_use_case():
    raise NotImplementedError


# ── 등록 ─────────────────────────────────────────────────────────


@router.post(
    "/agents/{agent_id}/jobs",
    response_model=EnqueueJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_job(
    agent_id: str,
    body: EnqueueJobRequest,
    auth_ctx: AuthContext = Depends(get_auth_context),
    use_case=Depends(get_enqueue_job_use_case),
):
    """백그라운드 작업 등록 — 즉시 202 접수, 실행은 워커 루프가 담당."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(
            agent_id,
            body,
            str(auth_ctx.user_id),
            list(auth_ctx.department_ids),
            request_id,
        )
    except JobConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except JobNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )


# ── 조회·확인 (D14: 리터럴 경로 선행 선언) ─────────────────────────


@router.get("/jobs/unseen-count", response_model=UnseenCountResponse)
async def count_unseen_jobs(
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_count_unseen_use_case),
):
    request_id = str(uuid.uuid4())
    return await use_case.execute(str(current_user.id), request_id)


@router.post("/jobs/seen-all", response_model=SeenAllResponse)
async def mark_all_jobs_seen(
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_mark_all_seen_use_case),
):
    request_id = str(uuid.uuid4())
    return await use_case.execute(str(current_user.id), request_id)


@router.get("/jobs", response_model=list[JobResponse])
async def list_jobs(
    status_filter: str | None = Query(
        default=None,
        alias="status",
        pattern="^(queued|running|success|failed)$",
    ),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_list_jobs_use_case),
):
    request_id = str(uuid.uuid4())
    return await use_case.execute(
        str(current_user.id), status_filter, limit, offset, request_id
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_get_job_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(job_id, str(current_user.id), request_id)
    except JobNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )


@router.post("/jobs/{job_id}/seen", status_code=status.HTTP_204_NO_CONTENT)
async def mark_job_seen(
    job_id: str,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_mark_seen_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        await use_case.execute(job_id, str(current_user.id), request_id)
    except JobNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )


# ── 스케줄 실행 이력 (D9 — 작업함 스케줄 탭) ───────────────────────


@router.get("/schedule-runs", response_model=list[MyScheduleRunResponse])
async def list_my_schedule_runs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_list_my_schedule_runs_use_case),
):
    request_id = str(uuid.uuid4())
    return await use_case.execute(
        str(current_user.id), limit, offset, request_id
    )
