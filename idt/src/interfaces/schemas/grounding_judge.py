"""관리자 근거 판정 모델 설정 요청·응답 (answer-citation-verification Design §4.2)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from src.domain.grounding_judge_setting.models import (
    EffectiveJudgeModel,
    GroundingJudgeSetting,
)


class GroundingJudgeSettingRequest(BaseModel):
    judge_llm_model_id: str | None = None


class EffectiveJudgeModelResponse(BaseModel):
    model_id: str
    model_name: str
    display_name: str
    source: Literal["admin", "env", "default"]


class GroundingJudgeSettingResponse(BaseModel):
    judge_llm_model_id: str | None
    effective: EffectiveJudgeModelResponse | None

    @classmethod
    def from_domain(
        cls, setting: GroundingJudgeSetting, effective: EffectiveJudgeModel | None
    ) -> GroundingJudgeSettingResponse:
        return cls(
            judge_llm_model_id=setting.judge_llm_model_id,
            effective=(
                EffectiveJudgeModelResponse(
                    model_id=effective.model_id,
                    model_name=effective.model_name,
                    display_name=effective.display_name,
                    source=effective.source,
                )
                if effective is not None
                else None
            ),
        )
