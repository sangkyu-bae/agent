"""RAGAS 평가 Application DTO."""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class BatchEvalRequest:
    target_type: str
    metrics: list[str]
    testcases: list[dict]
    top_k: int = 5
    sample_ratio: float = 1.0
    llm_model: str = "gpt-4o-mini"
    agent_id: str | None = None
    collection_name: str | None = None


@dataclass(frozen=True)
class BatchEvalResponse:
    run_id: str
    status: str
    total_cases: int
    message: str


@dataclass(frozen=True)
class RealtimeEvalRequest:
    question: str
    answer: str
    contexts: list[str]
    ground_truth: str | None = None
    metrics: list[str] = field(
        default_factory=lambda: ["faithfulness", "answer_relevancy"]
    )
    target_type: str = "rag"


@dataclass(frozen=True)
class RealtimeEvalResponse:
    result_id: str
    scores: dict[str, float]


@dataclass(frozen=True)
class EvalRunDetailResponse:
    id: str
    eval_type: str
    target_type: str
    status: str
    total_cases: int
    created_at: datetime
    completed_at: datetime | None
    summary: dict[str, float]


@dataclass(frozen=True)
class EvalResultItem:
    id: str
    question: str
    answer: str
    ground_truth: str | None
    scores: dict[str, float]
    created_at: datetime


@dataclass(frozen=True)
class TestsetUploadRequest:
    name: str
    description: str
    cases: list[dict]


@dataclass(frozen=True)
class TestsetResponse:
    id: str
    name: str
    description: str
    case_count: int
    created_at: datetime
