"""RAGAS 평가 도메인 Value Objects."""
from dataclasses import dataclass, field
from enum import Enum


class MetricType(str, Enum):
    """지원 평가 지표 목록."""

    FAITHFULNESS = "faithfulness"
    ANSWER_RELEVANCY = "answer_relevancy"
    CONTEXT_PRECISION = "context_precision"
    CONTEXT_RECALL = "context_recall"
    ANSWER_CORRECTNESS = "answer_correctness"
    ANSWER_SIMILARITY = "answer_similarity"
    HIT_RATE = "hit_rate"
    MRR = "mrr"
    NDCG = "ndcg"


@dataclass(frozen=True)
class MetricScore:
    """단일 지표 점수."""

    metric: MetricType
    score: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"Score must be 0.0~1.0, got {self.score}")


@dataclass(frozen=True)
class TestCase:
    """테스트셋의 단일 케이스 (질문-정답 쌍)."""

    question: str
    ground_truth: str | None = None
    expected_contexts: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class EvalConfig:
    """평가 실행 설정."""

    metrics: list[MetricType]
    top_k: int = 5
    sample_ratio: float = 1.0
    llm_model: str = "gpt-4o-mini"
    collection_name: str | None = None
    agent_id: str | None = None
