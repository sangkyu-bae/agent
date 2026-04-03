"""Application 스키마: PlanRequest, PlanResponse."""
from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field

from src.domain.planner.schemas import PlanResult


class PlanRequest(BaseModel):
    query: str = Field(..., min_length=1)
    context: Dict[str, Any] = Field(default_factory=dict)
    request_id: str


class PlanResponse(BaseModel):
    query: str
    steps: List[Dict[str, Any]]
    confidence: float
    reasoning: str
    requires_clarification: bool
    clarifying_questions: List[str]
    request_id: str

    @classmethod
    def from_domain(cls, result: PlanResult, request_id: str) -> "PlanResponse":
        return cls(
            query=result.query,
            steps=[s.model_dump() for s in result.steps],
            confidence=result.confidence,
            reasoning=result.reasoning,
            requires_clarification=result.requires_clarification,
            clarifying_questions=result.clarifying_questions,
            request_id=request_id,
        )
