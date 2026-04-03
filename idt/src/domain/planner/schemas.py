"""도메인 스키마: PlanStep, PlanResult (Value Object, frozen)."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    """단일 실행 단계 Value Object."""

    model_config = {"frozen": True}

    step_index: int = Field(..., ge=0, description="단계 순서 (0부터)")
    description: str = Field(..., min_length=1, description="이 단계에서 할 일")
    tool_ids: List[str] = Field(default_factory=list, description="필요한 도구 ID 목록")
    search_strategy: Optional[str] = Field(
        default=None,
        description="vector | bm25 | hybrid | None",
    )
    expected_output: str = Field(..., min_length=1, description="이 단계의 예상 출력")


class PlanResult(BaseModel):
    """전체 실행 계획 Value Object."""

    model_config = {"frozen": True}

    query: str = Field(..., min_length=1)
    steps: List[PlanStep] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str = Field(default="")
    requires_clarification: bool = Field(default=False)
    clarifying_questions: List[str] = Field(default_factory=list)
