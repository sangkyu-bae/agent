"""Output schemas for hallucination evaluation."""

from typing import Literal

from pydantic import BaseModel, Field


class HallucinationOutput(BaseModel):
    """Structured output schema for LLM hallucination evaluation.

    Used with ChatOpenAI.with_structured_output() to enforce structured responses.

    Attributes:
        is_hallucinated: True if the LLM generation is hallucinated (not grounded in documents),
                         False if grounded.
    """

    is_hallucinated: bool = Field(
        ...,
        description="Whether the LLM generation is hallucinated (not grounded in provided documents)"
    )


# ── draft-grounding-check v0.2 §4.1: 주장 단위 근거 판정 ─────────────


class ClaimOut(BaseModel):
    """근거로 확인되지 않은 주장 1건."""

    span: str = Field(..., description="생성문에서 그대로 복사한 문제 구간 (요약·의역 금지)")
    reason: str = Field(..., description="근거로 확인되지 않는 이유 (한 문장)")
    severity: Literal["high", "low"] = Field(
        ...,
        description="high=고객이 그대로 행동하게 되는 구체 사실, low=일반 상식·인사·일반 안내",
    )


class GroundingJudgeOutput(BaseModel):
    """근거 판정 결과 — 문제가 없으면 빈 목록."""

    unsupported_claims: list[ClaimOut] = Field(default_factory=list)
