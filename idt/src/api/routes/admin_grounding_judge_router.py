"""Admin grounding-judge router: /api/v1/admin/grounding-judge/*.

Design Ref: answer-citation-verification §4.2 — 라우터는 변환·오류 매핑만 한다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.application.grounding_judge_setting.use_cases import (
    GroundingJudgeSettingUseCase,
)
from src.domain.auth.entities import User
from src.domain.grounding_judge_setting.exceptions import GroundingJudgeSettingError
from src.interfaces.dependencies.auth import require_role
from src.interfaces.schemas.grounding_judge import (
    GroundingJudgeSettingRequest,
    GroundingJudgeSettingResponse,
)

router = APIRouter(
    prefix="/api/v1/admin/grounding-judge", tags=["admin-grounding-judge"]
)


def get_grounding_judge_setting_use_case() -> GroundingJudgeSettingUseCase:
    raise NotImplementedError(
        "GroundingJudgeSettingUseCase not wired (wire_grounding_judge)"
    )


def _request_id(user: User) -> str:
    return f"admin-grounding-judge-{user.id}"


@router.get("/settings", response_model=GroundingJudgeSettingResponse)
async def get_settings(
    current_user: User = Depends(require_role("admin")),
    use_case: GroundingJudgeSettingUseCase = Depends(
        get_grounding_judge_setting_use_case
    ),
) -> GroundingJudgeSettingResponse:
    setting, effective = await use_case.get(_request_id(current_user))
    return GroundingJudgeSettingResponse.from_domain(setting, effective)


@router.put("/settings", response_model=GroundingJudgeSettingResponse)
async def put_settings(
    body: GroundingJudgeSettingRequest,
    current_user: User = Depends(require_role("admin")),
    use_case: GroundingJudgeSettingUseCase = Depends(
        get_grounding_judge_setting_use_case
    ),
) -> GroundingJudgeSettingResponse:
    try:
        setting, effective = await use_case.update(
            body.judge_llm_model_id,
            actor_id=str(current_user.id),
            request_id=_request_id(current_user),
        )
    except GroundingJudgeSettingError as e:
        raise HTTPException(
            status_code=422, detail={"code": e.code, "message": str(e)}
        ) from e
    return GroundingJudgeSettingResponse.from_domain(setting, effective)
