"""RAGAS 평가 Application DTO."""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class BatchEvalRequest:
    target_type: str
    metrics: list[str]
    testcases: list[dict] = field(default_factory=list)
    testset_id: str | None = None  # testcases와 배타 — 정확히 하나만 제공
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
    error_message: str | None = None  # 실패 원인 표면화 (에러 은닉 금지)
    config: dict = field(default_factory=dict)  # 재실행 프리필용
    # agent-model-benchmark §4.3 / G-10: 스윕 소속 식별. 단독 실행이면 둘 다 None.
    sweep_id: str | None = None
    llm_model_id: str | None = None


@dataclass(frozen=True)
class EvalResultItem:
    id: str
    question: str
    answer: str
    ground_truth: str | None
    contexts: list[str]
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
    user_id: str | None = None


@dataclass(frozen=True)
class TestsetDetailResponse:
    id: str
    name: str
    description: str
    case_count: int
    created_at: datetime
    user_id: str | None = None
    cases: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class GeneratedTestsetDraft:
    """문서→QA 생성 초안 — 사용자 검토 전까지 저장하지 않는다."""

    source_filename: str
    items: list[dict] = field(default_factory=list)
