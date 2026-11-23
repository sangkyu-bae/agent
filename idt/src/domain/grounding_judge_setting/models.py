"""근거 판정 모델 전역 설정 VO.

Design Ref: answer-citation-verification §2.2 D-15·D-16 — 관리자가 고른 모델이
근거 판정(답변·초안)과 인용 검증에 함께 쓰인다. 비어 있으면 env 설정을 따른다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# admin: 관리자 설정 모델 / env: GROUNDING_JUDGE_MODEL / default: 기본 모델
JudgeModelSource = Literal["admin", "env", "default"]


@dataclass(frozen=True)
class GroundingJudgeSetting:
    judge_llm_model_id: str | None = None
    updated_by: str | None = None


@dataclass(frozen=True)
class EffectiveJudgeModel:
    """지금 실제로 판정에 쓰이는 모델 — 관리자 화면 표시용."""

    model_id: str
    model_name: str
    display_name: str
    source: JudgeModelSource
