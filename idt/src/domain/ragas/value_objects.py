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
    # agent-model-benchmark §3.4 / D6: 이 케이스에서 호출되어야 할 도구 이름.
    # 미기재(None/빈 리스트)면 도구 정확도를 N/A로 두고 집계에서 제외한다(FR-15).
    expected_tools: list[str] | None = None


@dataclass(frozen=True)
class EvalConfig:
    """평가 실행 설정."""

    metrics: list[MetricType]
    top_k: int = 5
    sample_ratio: float = 1.0
    llm_model: str = "gpt-4o-mini"
    collection_name: str | None = None
    agent_id: str | None = None
    # agent-model-benchmark D1: 스윕이 에이전트 정의를 건드리지 않고 모델만 교체한다.
    # None이면 기존 동작(에이전트에 저장된 모델) 그대로.
    llm_model_id_override: str | None = None
    # D9: 0.0은 falsy이므로 소비 측에서 `is not None`으로 판정한다.
    temperature_override: float | None = None
    # D4: RAGAS 채점 judge 모델명. None이면 RAGAS 라이브러리 기본값.
    judge_llm_model: str | None = None
    # D2: 평가 실행이 conversation_message를 남기지 않게 한다.
    persist_conversation: bool = True


@dataclass(frozen=True)
class TargetExecution:
    """평가 대상 1회 실행 결과.

    agent-model-benchmark: 기존 (answer, contexts, extra_scores) 튜플을 대체한다.
    스윕은 답변뿐 아니라 **어떤 도구를 불렀는지(tools_used)**와 **어느 관측 실행에
    대응하는지(ai_run_id)**를 알아야 도구 F1·비용·지연을 회수할 수 있다 (D6/D10).
    agent 대상이 아닌 rag/retrieval에서는 두 필드가 None으로 남는다.
    """

    answer: str
    contexts: list[str] = field(default_factory=list)
    extra_scores: dict[str, float] = field(default_factory=dict)
    tools_used: list[str] | None = None
    ai_run_id: str | None = None
