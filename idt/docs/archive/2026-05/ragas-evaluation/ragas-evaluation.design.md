# Design: RAGAS Evaluation Module

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | RAGAS 기반 RAG/Agent 평가측정 모듈 |
| Plan 참조 | `docs/01-plan/features/ragas-evaluation.plan.md` |
| 작성일 | 2026-05-13 |

### Value Delivered

| 관점 | 내용 |
|------|------|
| **Problem** | RAG/Agent 품질을 정량적으로 측정할 수단이 없어 개선 방향을 판단할 수 없다 |
| **Solution** | RAGAS 프레임워크 기반 독립 평가 모듈 — 배치 + 실시간 모니터링 |
| **Function UX Effect** | 테스트셋 일괄 평가 → 점수 리포트 / 실시간 질의 시 백그라운드 평가 기록 |
| **Core Value** | 데이터 기반 RAG·Agent 품질 개선 사이클 확립 |

---

## 1. 디렉토리 구조

```
src/
├── domain/ragas/
│   ├── __init__.py
│   ├── entities.py              # EvaluationRun, EvaluationResult (도메인 엔티티)
│   ├── value_objects.py         # MetricScore, TestCase, EvalConfig, MetricType
│   ├── interfaces.py            # EvaluationRepositoryInterface, EvaluatorInterface
│   └── policies.py              # EvaluationPolicy (실행 조건, 임계값)
│
├── application/ragas/
│   ├── __init__.py
│   ├── batch_eval_use_case.py   # BatchEvaluationUseCase
│   ├── realtime_eval_use_case.py# RealtimeEvaluationUseCase
│   ├── eval_result_use_case.py  # EvalResultUseCase (조회/통계)
│   ├── testset_use_case.py      # TestsetUseCase (테스트셋 CRUD)
│   └── schemas.py               # 요청/응답 DTO (Application 경계)
│
├── infrastructure/ragas/
│   ├── __init__.py
│   ├── ragas_adapter.py         # RagasEvaluatorAdapter (RAGAS 라이브러리 래핑)
│   ├── retrieval_metric_calculator.py  # RetrievalMetricCalculator (Hit Rate, MRR, NDCG)
│   ├── models.py                # SQLAlchemy ORM 모델
│   └── repository.py            # EvaluationRepository (MySQL CRUD)
│
├── api/routes/
│   └── ragas_router.py          # REST API 엔드포인트
│
└── tests/
    ├── domain/ragas/
    │   ├── test_entities.py
    │   ├── test_value_objects.py
    │   └── test_policies.py
    ├── application/ragas/
    │   ├── test_batch_eval_use_case.py
    │   ├── test_realtime_eval_use_case.py
    │   ├── test_eval_result_use_case.py
    │   └── test_testset_use_case.py
    └── infrastructure/ragas/
        ├── test_ragas_adapter.py
        ├── test_retrieval_metric_calculator.py
        └── test_repository.py
```

---

## 2. Domain Layer

### 2.1 entities.py

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

EvalType = Literal["batch", "realtime"]
TargetType = Literal["rag", "agent", "retrieval"]
RunStatus = Literal["pending", "running", "completed", "failed"]


@dataclass
class EvaluationRun:
    """평가 실행 단위. 배치 1회 또는 실시간 평가 그룹."""

    id: str
    eval_type: EvalType
    target_type: TargetType
    status: RunStatus
    total_cases: int
    created_at: datetime
    target_id: str | None = None
    config: dict = field(default_factory=dict)
    completed_at: datetime | None = None
    error_message: str | None = None

    def mark_completed(self, completed_at: datetime) -> None:
        self.status = "completed"
        self.completed_at = completed_at

    def mark_failed(self, error_message: str, failed_at: datetime) -> None:
        self.status = "failed"
        self.error_message = error_message
        self.completed_at = failed_at


@dataclass
class EvaluationResult:
    """개별 질문-답변 쌍의 평가 결과."""

    id: str
    run_id: str
    question: str
    answer: str
    contexts: list[str]
    created_at: datetime
    ground_truth: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)
```

### 2.2 value_objects.py

```python
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
```

### 2.3 interfaces.py

```python
from abc import ABC, abstractmethod

from src.domain.ragas.entities import EvaluationResult, EvaluationRun


class EvaluationRepositoryInterface(ABC):
    """평가 결과 저장소 인터페이스."""

    @abstractmethod
    async def save_run(self, run: EvaluationRun, request_id: str) -> EvaluationRun: ...

    @abstractmethod
    async def update_run(self, run: EvaluationRun, request_id: str) -> None: ...

    @abstractmethod
    async def get_run(self, run_id: str, request_id: str) -> EvaluationRun | None: ...

    @abstractmethod
    async def list_runs(
        self,
        target_type: str | None,
        eval_type: str | None,
        limit: int,
        offset: int,
        request_id: str,
    ) -> tuple[list[EvaluationRun], int]: ...

    @abstractmethod
    async def delete_run(self, run_id: str, request_id: str) -> bool: ...

    @abstractmethod
    async def save_result(self, result: EvaluationResult, request_id: str) -> None: ...

    @abstractmethod
    async def save_results_bulk(
        self, results: list[EvaluationResult], request_id: str
    ) -> None: ...

    @abstractmethod
    async def get_results_by_run(
        self, run_id: str, limit: int, offset: int, request_id: str
    ) -> tuple[list[EvaluationResult], int]: ...

    @abstractmethod
    async def get_run_summary(
        self, run_id: str, request_id: str
    ) -> dict[str, float]: ...


class EvaluatorInterface(ABC):
    """평가 실행 엔진 인터페이스 (RAGAS 어댑터가 구현)."""

    @abstractmethod
    async def evaluate(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        ground_truth: str | None,
        metrics: list[str],
        request_id: str,
    ) -> dict[str, float]: ...
```

### 2.4 policies.py

```python
from src.domain.ragas.value_objects import EvalConfig, MetricType, TestCase

METRICS_REQUIRING_GROUND_TRUTH = {
    MetricType.CONTEXT_RECALL,
    MetricType.ANSWER_CORRECTNESS,
    MetricType.ANSWER_SIMILARITY,
}

METRICS_REQUIRING_LLM = {
    MetricType.FAITHFULNESS,
    MetricType.ANSWER_RELEVANCY,
    MetricType.CONTEXT_PRECISION,
    MetricType.CONTEXT_RECALL,
    MetricType.ANSWER_CORRECTNESS,
    MetricType.ANSWER_SIMILARITY,
}


class EvaluationPolicy:
    """평가 실행 정책."""

    @staticmethod
    def validate_config(config: EvalConfig) -> list[str]:
        """설정 유효성 검증. 위반 사항 목록 반환."""
        errors: list[str] = []
        if not config.metrics:
            errors.append("최소 1개 이상의 평가 지표가 필요합니다")
        if config.top_k < 1:
            errors.append("top_k는 1 이상이어야 합니다")
        if not 0.0 < config.sample_ratio <= 1.0:
            errors.append("sample_ratio는 0.0 초과 1.0 이하여야 합니다")
        return errors

    @staticmethod
    def validate_testcases(
        cases: list[TestCase], config: EvalConfig
    ) -> list[str]:
        """테스트 케이스 유효성 검증."""
        errors: list[str] = []
        if not cases:
            errors.append("테스트 케이스가 비어있습니다")
            return errors

        needs_gt = bool(METRICS_REQUIRING_GROUND_TRUTH & set(config.metrics))
        for i, case in enumerate(cases):
            if not case.question.strip():
                errors.append(f"케이스 {i}: 질문이 비어있습니다")
            if needs_gt and not case.ground_truth:
                errors.append(
                    f"케이스 {i}: 선택한 지표에 ground_truth가 필요합니다"
                )
        return errors

    @staticmethod
    def requires_ground_truth(metrics: list[MetricType]) -> bool:
        """선택한 지표 중 ground_truth 필요 여부."""
        return bool(METRICS_REQUIRING_GROUND_TRUTH & set(metrics))

    @staticmethod
    def is_passing(scores: dict[str, float], threshold: float = 0.7) -> bool:
        """평균 점수가 임계값 이상인지 판정."""
        if not scores:
            return False
        avg = sum(scores.values()) / len(scores)
        return avg >= threshold
```

---

## 3. Application Layer

### 3.1 schemas.py (요청/응답 DTO)

```python
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class BatchEvalRequest:
    """배치 평가 요청."""

    target_type: str                          # "rag" | "agent" | "retrieval"
    metrics: list[str]                        # ["faithfulness", "answer_relevancy", ...]
    testcases: list[dict]                     # [{"question": ..., "ground_truth": ...}]
    top_k: int = 5
    sample_ratio: float = 1.0
    llm_model: str = "gpt-4o-mini"
    agent_id: str | None = None               # Agent 평가 시
    collection_name: str | None = None        # RAG 검색 대상 컬렉션


@dataclass(frozen=True)
class BatchEvalResponse:
    """배치 평가 응답 (비동기 시작)."""

    run_id: str
    status: str
    total_cases: int
    message: str


@dataclass(frozen=True)
class RealtimeEvalRequest:
    """실시간 평가 요청."""

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
    """실시간 평가 응답."""

    result_id: str
    scores: dict[str, float]


@dataclass(frozen=True)
class EvalRunDetailResponse:
    """평가 실행 상세 응답."""

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
    """개별 평가 결과 항목."""

    id: str
    question: str
    answer: str
    ground_truth: str | None
    scores: dict[str, float]
    created_at: datetime


@dataclass(frozen=True)
class TestsetUploadRequest:
    """테스트셋 업로드 요청."""

    name: str
    description: str
    cases: list[dict]     # [{"question": ..., "ground_truth": ...}]


@dataclass(frozen=True)
class TestsetResponse:
    """테스트셋 응답."""

    id: str
    name: str
    description: str
    case_count: int
    created_at: datetime
```

### 3.2 batch_eval_use_case.py

```python
class BatchEvaluationUseCase:
    """테스트셋 기반 일괄 평가 UseCase.

    플로우:
    1. EvalConfig + TestCase 유효성 검증 (Policy)
    2. EvaluationRun 생성 (status=pending)
    3. BackgroundTasks에 실제 평가 로직 등록
    4. run_id 즉시 반환 (비동기)
    5. 백그라운드에서: 각 케이스별 검색→답변→평가→저장
    6. 완료 시 EvaluationRun status=completed
    """

    def __init__(
        self,
        repository: EvaluationRepositoryInterface,
        evaluator: EvaluatorInterface,
        hybrid_search_use_case: object,          # HybridSearchUseCase (인터페이스)
        rag_agent_use_case: object | None,       # RAGAgentUseCase (RAG 평가 시)
        run_agent_use_case: object | None,       # RunAgentUseCase (Agent 평가 시)
        logger: LoggerInterface,
    ) -> None: ...

    async def execute(
        self,
        request: BatchEvalRequest,
        request_id: str,
    ) -> BatchEvalResponse:
        """평가 실행 생성 + 반환. 실제 평가는 _run_evaluation에서 비동기 실행."""
        ...

    async def run_evaluation(
        self,
        run_id: str,
        config: EvalConfig,
        testcases: list[TestCase],
        request_id: str,
    ) -> None:
        """백그라운드 평가 실행 로직.

        각 테스트 케이스에 대해:
        1. target_type에 따라 검색/답변 생성
           - rag: HybridSearch → RAGAgent
           - agent: RunAgent (agent_id 기반)
           - retrieval: HybridSearch만
        2. evaluator.evaluate() 호출
        3. EvaluationResult DB 저장
        """
        ...
```

### 3.3 realtime_eval_use_case.py

```python
class RealtimeEvaluationUseCase:
    """실시간 단건 평가 UseCase.

    기존 RAG/Agent 응답 후 호출됨. 질문, 답변, contexts를 받아
    선택된 지표로 평가한 후 DB 저장.
    """

    def __init__(
        self,
        repository: EvaluationRepositoryInterface,
        evaluator: EvaluatorInterface,
        logger: LoggerInterface,
    ) -> None: ...

    async def execute(
        self, request: RealtimeEvalRequest, request_id: str
    ) -> RealtimeEvalResponse:
        """단건 평가 실행 및 결과 저장."""
        ...
```

### 3.4 eval_result_use_case.py

```python
class EvalResultUseCase:
    """평가 결과 조회 UseCase."""

    def __init__(
        self,
        repository: EvaluationRepositoryInterface,
        logger: LoggerInterface,
    ) -> None: ...

    async def get_run_detail(
        self, run_id: str, request_id: str
    ) -> EvalRunDetailResponse:
        """실행 상세 + 요약 통계 조회."""
        ...

    async def list_runs(
        self,
        target_type: str | None,
        eval_type: str | None,
        limit: int,
        offset: int,
        request_id: str,
    ) -> tuple[list[EvalRunDetailResponse], int]:
        """실행 이력 목록 조회."""
        ...

    async def get_results(
        self, run_id: str, limit: int, offset: int, request_id: str
    ) -> tuple[list[EvalResultItem], int]:
        """개별 결과 목록 조회."""
        ...

    async def delete_run(self, run_id: str, request_id: str) -> bool:
        """실행 삭제."""
        ...

    async def get_recent_realtime(
        self, limit: int, request_id: str
    ) -> list[EvalResultItem]:
        """최근 실시간 평가 결과 조회."""
        ...
```

### 3.5 testset_use_case.py

```python
class TestsetUseCase:
    """테스트셋 CRUD UseCase."""

    def __init__(
        self,
        repository: EvaluationRepositoryInterface,
        logger: LoggerInterface,
    ) -> None: ...

    async def create(
        self, request: TestsetUploadRequest, request_id: str
    ) -> TestsetResponse: ...

    async def list_all(
        self, limit: int, offset: int, request_id: str
    ) -> tuple[list[TestsetResponse], int]: ...

    async def get_detail(
        self, testset_id: str, request_id: str
    ) -> TestsetResponse | None: ...

    async def delete(
        self, testset_id: str, request_id: str
    ) -> bool: ...
```

---

## 4. Infrastructure Layer

### 4.1 models.py (SQLAlchemy ORM)

```python
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.persistence.models.base import Base


class EvaluationRunModel(Base):
    __tablename__ = "evaluation_run"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    eval_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    total_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    results: Mapped[list["EvaluationResultModel"]] = relationship(
        "EvaluationResultModel",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class EvaluationResultModel(Base):
    __tablename__ = "evaluation_result"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("evaluation_run.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    ground_truth: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    contexts: Mapped[list] = mapped_column(JSON, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    run: Mapped["EvaluationRunModel"] = relationship(back_populates="results")


class TestsetModel(Base):
    __tablename__ = "evaluation_testset"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cases: Mapped[list] = mapped_column(JSON, nullable=False)
    case_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
```

**설계 결정 — 평가 점수를 `metrics` JSON 컬럼으로 통합:**

Plan에서는 `faithfulness`, `answer_relevancy` 등을 개별 FLOAT 컬럼으로 정의했으나,
새로운 지표 추가 시마다 ALTER TABLE이 필요한 문제가 있어 `metrics JSON` 단일 컬럼으로 통합한다.

- 장점: 새 지표 추가 시 DB 스키마 변경 불필요, 유연성 확보
- 단점: JSON 내부 필드 인덱싱 불가 (MySQL JSON 인덱스로 보완 가능)
- 요약 통계는 application layer에서 계산

마찬가지로 Plan의 `evaluation_summaries` 테이블은 별도 테이블 대신
`EvalResultUseCase.get_run_detail()`에서 `evaluation_result` 행을 집계하여 반환한다.
초기에는 테이블 수를 줄여 단순하게 유지하고, 성능 이슈 발생 시 materialized summary 테이블을 추가한다.

### 4.2 ragas_adapter.py

```python
class RagasEvaluatorAdapter(EvaluatorInterface):
    """RAGAS 라이브러리를 래핑한 평가 어댑터.

    RAGAS 0.2+ API 기준:
    - ragas.evaluate() 호출
    - Dataset 변환 처리
    - 결과를 dict[str, float]로 반환
    """

    def __init__(self, llm_model: str = "gpt-4o-mini") -> None:
        self._logger = get_logger(__name__)
        self._llm_model = llm_model

    async def evaluate(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        ground_truth: str | None,
        metrics: list[str],
        request_id: str,
    ) -> dict[str, float]:
        """RAGAS 지표 계산.

        1. metrics 목록에서 RAGAS Metric 객체 매핑
        2. 입력 데이터를 RAGAS Dataset 형식으로 변환
        3. ragas.evaluate() 호출
        4. 결과를 {metric_name: score} dict로 반환
        """
        ...

    def _map_metrics(self, metric_names: list[str]) -> list:
        """MetricType 문자열 → RAGAS Metric 객체 매핑.

        지원 매핑:
        - faithfulness → Faithfulness()
        - answer_relevancy → AnswerRelevancy()
        - context_precision → ContextPrecision()
        - context_recall → ContextRecall()
        - answer_correctness → AnswerCorrectness()
        - answer_similarity → AnswerSimilarity()
        """
        ...
```

### 4.3 retrieval_metric_calculator.py

```python
class RetrievalMetricCalculator:
    """커스텀 Retrieval 품질 지표 계산기.

    RAGAS에 포함되지 않는 retrieval 전용 지표:
    - Hit Rate: 정답 문서가 top-k에 포함되는 비율
    - MRR: 정답 문서의 평균 역순위
    - NDCG: 정규화 할인 누적 이득
    """

    @staticmethod
    def hit_rate(
        retrieved_ids: list[str], relevant_ids: list[str]
    ) -> float:
        """top-k 결과에 정답 문서가 포함되는지 여부 (0.0 or 1.0)."""
        ...

    @staticmethod
    def mrr(
        retrieved_ids: list[str], relevant_ids: list[str]
    ) -> float:
        """첫 번째 관련 문서의 역순위. 없으면 0.0."""
        ...

    @staticmethod
    def ndcg(
        retrieved_ids: list[str],
        relevant_ids: list[str],
        k: int | None = None,
    ) -> float:
        """Normalized Discounted Cumulative Gain."""
        ...
```

### 4.4 repository.py

```python
class EvaluationRepository(EvaluationRepositoryInterface):
    """MySQL 기반 평가 결과 저장소.

    DB-001 규칙 준수:
    - session은 외부에서 주입 (Depends(get_session))
    - commit/rollback 호출 금지
    - flush()만 사용
    """

    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save_run(self, run: EvaluationRun, request_id: str) -> EvaluationRun:
        """EvaluationRun 저장. model 변환 → session.add → flush."""
        ...

    async def update_run(self, run: EvaluationRun, request_id: str) -> None:
        """EvaluationRun 상태 업데이트."""
        ...

    async def get_run(self, run_id: str, request_id: str) -> EvaluationRun | None:
        """run_id로 조회."""
        ...

    async def list_runs(
        self, target_type, eval_type, limit, offset, request_id
    ) -> tuple[list[EvaluationRun], int]:
        """필터 + 페이지네이션 조회."""
        ...

    async def delete_run(self, run_id: str, request_id: str) -> bool:
        """CASCADE로 결과까지 삭제."""
        ...

    async def save_result(self, result: EvaluationResult, request_id: str) -> None:
        """단건 결과 저장."""
        ...

    async def save_results_bulk(
        self, results: list[EvaluationResult], request_id: str
    ) -> None:
        """배치 결과 일괄 저장."""
        ...

    async def get_results_by_run(
        self, run_id, limit, offset, request_id
    ) -> tuple[list[EvaluationResult], int]:
        """run_id별 결과 목록 조회."""
        ...

    async def get_run_summary(self, run_id: str, request_id: str) -> dict[str, float]:
        """run_id별 지표 평균 계산.

        evaluation_result 행을 순회하며 metrics JSON 필드의 각 키별 평균을 계산.
        """
        ...

    # -- Testset CRUD --

    async def save_testset(self, model: TestsetModel, request_id: str) -> None: ...
    async def list_testsets(self, limit, offset, request_id) -> tuple[list, int]: ...
    async def get_testset(self, testset_id, request_id): ...
    async def delete_testset(self, testset_id, request_id) -> bool: ...
```

---

## 5. API Layer

### 5.1 ragas_router.py

```python
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.persistence.database import get_session

router = APIRouter(prefix="/api/ragas", tags=["RAGAS Evaluation"])


# ── 배치 평가 ──

@router.post("/batch", status_code=202)
async def create_batch_evaluation(
    body: BatchEvalRequestBody,
    background_tasks: BackgroundTasks,
    use_case: BatchEvaluationUseCase = Depends(get_batch_eval_use_case),
    request_id: str = Depends(get_request_id),
) -> BatchEvalResponseBody:
    """테스트셋 기반 배치 평가 시작. 202 Accepted + run_id 반환."""
    ...


@router.get("/runs")
async def list_evaluation_runs(
    target_type: str | None = Query(None),
    eval_type: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    use_case: EvalResultUseCase = Depends(get_eval_result_use_case),
    request_id: str = Depends(get_request_id),
) -> PaginatedResponse:
    """평가 실행 이력 목록 조회."""
    ...


@router.get("/runs/{run_id}")
async def get_evaluation_run(
    run_id: str,
    use_case: EvalResultUseCase = Depends(get_eval_result_use_case),
    request_id: str = Depends(get_request_id),
) -> EvalRunDetailResponseBody:
    """평가 실행 상세 + 요약 통계."""
    ...


@router.get("/runs/{run_id}/results")
async def get_evaluation_results(
    run_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    use_case: EvalResultUseCase = Depends(get_eval_result_use_case),
    request_id: str = Depends(get_request_id),
) -> PaginatedResponse:
    """개별 케이스별 결과 목록."""
    ...


@router.delete("/runs/{run_id}", status_code=204)
async def delete_evaluation_run(
    run_id: str,
    use_case: EvalResultUseCase = Depends(get_eval_result_use_case),
    request_id: str = Depends(get_request_id),
) -> None:
    """평가 실행 삭제 (결과 CASCADE 삭제)."""
    ...


# ── 실시간 평가 ──

@router.post("/realtime/evaluate")
async def realtime_evaluate(
    body: RealtimeEvalRequestBody,
    use_case: RealtimeEvaluationUseCase = Depends(get_realtime_eval_use_case),
    request_id: str = Depends(get_request_id),
) -> RealtimeEvalResponseBody:
    """단건 실시간 평가."""
    ...


@router.get("/realtime/recent")
async def get_recent_realtime(
    limit: int = Query(20, ge=1, le=100),
    use_case: EvalResultUseCase = Depends(get_eval_result_use_case),
    request_id: str = Depends(get_request_id),
) -> list[EvalResultItemBody]:
    """최근 실시간 평가 결과."""
    ...


# ── 테스트셋 관리 ──

@router.post("/testsets", status_code=201)
async def create_testset(
    body: TestsetUploadRequestBody,
    use_case: TestsetUseCase = Depends(get_testset_use_case),
    request_id: str = Depends(get_request_id),
) -> TestsetResponseBody:
    """테스트셋 업로드."""
    ...


@router.get("/testsets")
async def list_testsets(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    use_case: TestsetUseCase = Depends(get_testset_use_case),
    request_id: str = Depends(get_request_id),
) -> PaginatedResponse:
    """테스트셋 목록."""
    ...


@router.get("/testsets/{testset_id}")
async def get_testset(
    testset_id: str,
    use_case: TestsetUseCase = Depends(get_testset_use_case),
    request_id: str = Depends(get_request_id),
) -> TestsetResponseBody:
    """테스트셋 상세."""
    ...


@router.delete("/testsets/{testset_id}", status_code=204)
async def delete_testset(
    testset_id: str,
    use_case: TestsetUseCase = Depends(get_testset_use_case),
    request_id: str = Depends(get_request_id),
) -> None:
    """테스트셋 삭제."""
    ...
```

### 5.2 DI 등록 (main.py 추가 사항)

```python
# main.py에 추가할 DI 팩토리 패턴

def _make_eval_repo(session: AsyncSession):
    return EvaluationRepository(session=session, logger=structured_logger)

def _make_evaluator():
    return RagasEvaluatorAdapter(llm_model="gpt-4o-mini")

def batch_eval_factory(session: AsyncSession = Depends(get_session)):
    return BatchEvaluationUseCase(
        repository=_make_eval_repo(session),
        evaluator=_make_evaluator(),
        hybrid_search_use_case=...,    # 기존 DI에서 가져옴
        rag_agent_use_case=...,
        run_agent_use_case=None,
        logger=structured_logger,
    )

def realtime_eval_factory(session: AsyncSession = Depends(get_session)):
    return RealtimeEvaluationUseCase(
        repository=_make_eval_repo(session),
        evaluator=_make_evaluator(),
        logger=structured_logger,
    )

def eval_result_factory(session: AsyncSession = Depends(get_session)):
    return EvalResultUseCase(
        repository=_make_eval_repo(session),
        logger=structured_logger,
    )

def testset_factory(session: AsyncSession = Depends(get_session)):
    return TestsetUseCase(
        repository=_make_eval_repo(session),
        logger=structured_logger,
    )
```

---

## 6. 시퀀스 다이어그램

### 6.1 배치 평가

```
Client          Router           BatchEvalUC      Policy     Repo        Evaluator
  │                │                  │              │         │             │
  │ POST /batch    │                  │              │         │             │
  ├───────────────►│                  │              │         │             │
  │                │  execute(req)    │              │         │             │
  │                ├─────────────────►│              │         │             │
  │                │                  │ validate()   │         │             │
  │                │                  ├─────────────►│         │             │
  │                │                  │   ok         │         │             │
  │                │                  │◄─────────────┤         │             │
  │                │                  │ save_run()   │         │             │
  │                │                  ├──────────────┼────────►│             │
  │                │                  │              │   ok    │             │
  │                │  202 + run_id    │◄─────────────┼─────────┤             │
  │◄───────────────┤                  │              │         │             │
  │                │                  │              │         │             │
  │      ┌─ BackgroundTask ──────────────────────────┼─────────┼─────────────┤
  │      │         │  run_evaluation()│              │         │             │
  │      │         │                  │              │         │             │
  │      │         │    for each case:│              │         │             │
  │      │         │    ├─ search ────┼──────────────┼─────────┼──► Hybrid   │
  │      │         │    ├─ generate ──┼──────────────┼─────────┼──► RAG/Agent│
  │      │         │    ├─ evaluate() │              │         │             │
  │      │         │    │             ├──────────────┼─────────┼────────────►│
  │      │         │    │             │   scores     │         │             │
  │      │         │    │             │◄─────────────┼─────────┼─────────────┤
  │      │         │    └─ save_result│              │         │             │
  │      │         │                  ├──────────────┼────────►│             │
  │      │         │  update_run(done)│              │         │             │
  │      │         │                  ├──────────────┼────────►│             │
  │      └─────────┤                  │              │         │             │
```

### 6.2 실시간 평가 (백그라운드 연동)

```
Client     RAG Router    RAGAgentUC    RealtimeEvalUC    Evaluator    Repo
  │            │              │               │              │          │
  │ POST /rag  │              │               │              │          │
  ├───────────►│  execute()   │               │              │          │
  │            ├─────────────►│               │              │          │
  │            │   response   │               │              │          │
  │◄───────────┤◄─────────────┤               │              │          │
  │            │              │               │              │          │
  │ ┌─ BackgroundTask ────────┤               │              │          │
  │ │          │              │  execute()    │              │          │
  │ │          │              ├──────────────►│  evaluate()  │          │
  │ │          │              │               ├─────────────►│          │
  │ │          │              │               │   scores     │          │
  │ │          │              │               │◄─────────────┤          │
  │ │          │              │               │  save_result │          │
  │ │          │              │               ├──────────────┼─────────►│
  │ └──────────┤              │               │              │          │
```

---

## 7. DB 마이그레이션

### 7.1 V014__create_evaluation_tables.sql

```sql
CREATE TABLE evaluation_run (
    id VARCHAR(36) PRIMARY KEY,
    eval_type VARCHAR(20) NOT NULL COMMENT 'batch | realtime',
    target_type VARCHAR(20) NOT NULL COMMENT 'rag | agent | retrieval',
    target_id VARCHAR(36) NULL COMMENT 'agent_id (Agent 평가 시)',
    status VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT 'pending | running | completed | failed',
    total_cases INT NOT NULL DEFAULT 0,
    config JSON NULL,
    error_message TEXT NULL,
    created_at DATETIME NOT NULL,
    completed_at DATETIME NULL,
    INDEX idx_eval_run_type (eval_type),
    INDEX idx_eval_run_target (target_type),
    INDEX idx_eval_run_status (status),
    INDEX idx_eval_run_created (created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE evaluation_result (
    id VARCHAR(36) PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL,
    question TEXT NOT NULL,
    ground_truth TEXT NULL,
    answer TEXT NOT NULL,
    contexts JSON NOT NULL,
    metrics JSON NOT NULL DEFAULT (JSON_OBJECT()),
    created_at DATETIME NOT NULL,
    CONSTRAINT fk_eval_result_run FOREIGN KEY (run_id)
        REFERENCES evaluation_run (id) ON DELETE CASCADE,
    INDEX idx_eval_result_run (run_id),
    INDEX idx_eval_result_created (created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE evaluation_testset (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT NULL,
    cases JSON NOT NULL,
    case_count INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    INDEX idx_testset_created (created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

## 8. 구현 순서 (TDD)

### Phase 1: Domain (테스트 → 구현)

| 순서 | 테스트 파일 | 구현 파일 | 항목 |
|------|-----------|----------|------|
| 1 | test_value_objects.py | value_objects.py | MetricType, MetricScore, TestCase, EvalConfig |
| 2 | test_entities.py | entities.py | EvaluationRun, EvaluationResult |
| 3 | test_policies.py | policies.py | EvaluationPolicy (validate_config, validate_testcases, is_passing) |
| 4 | — | interfaces.py | 인터페이스 정의 (테스트 불필요) |

### Phase 2: Infrastructure (테스트 → 구현)

| 순서 | 테스트 파일 | 구현 파일 | 항목 |
|------|-----------|----------|------|
| 5 | — | models.py | SQLAlchemy 모델 (선언적, 테스트는 repo 통합에서) |
| 6 | test_repository.py | repository.py | CRUD 통합 테스트 |
| 7 | test_retrieval_metric_calculator.py | retrieval_metric_calculator.py | Hit Rate, MRR, NDCG |
| 8 | test_ragas_adapter.py | ragas_adapter.py | RAGAS 래핑 (mock LLM) |

### Phase 3: Application (테스트 → 구현)

| 순서 | 테스트 파일 | 구현 파일 | 항목 |
|------|-----------|----------|------|
| 9 | test_batch_eval_use_case.py | batch_eval_use_case.py | 배치 평가 (repo/evaluator mock) |
| 10 | test_realtime_eval_use_case.py | realtime_eval_use_case.py | 실시간 평가 |
| 11 | test_eval_result_use_case.py | eval_result_use_case.py | 조회/통계 |
| 12 | test_testset_use_case.py | testset_use_case.py | 테스트셋 CRUD |

### Phase 4: API + DI (테스트 → 구현)

| 순서 | 항목 |
|------|------|
| 13 | ragas_router.py 엔드포인트 정의 |
| 14 | main.py DI 팩토리 등록 |
| 15 | DB 마이그레이션 실행 |
| 16 | E2E 수동 테스트 |

---

## 9. 설계 결정 기록

| 결정 | 선택 | 이유 |
|------|------|------|
| 평가 점수 저장 방식 | `metrics` JSON 단일 컬럼 | 새 지표 추가 시 스키마 변경 불필요 |
| 요약 통계 테이블 | 별도 테이블 없음 (쿼리 집계) | 초기 단순화, 성능 이슈 시 추가 |
| 배치 실행 방식 | FastAPI BackgroundTasks | 초기에는 Celery 없이 간단하게 구현 |
| RAGAS 호출 단위 | 건별 evaluate() | 배치 단위 호출보다 에러 격리 용이 |
| 실시간 평가 트리거 | 별도 API 엔드포인트 | 기존 RAG/Agent 코드 수정 최소화 (독립 우선) |
| Testset 저장 | MySQL JSON 컬럼 | 파일 관리 복잡도 회피, 소규모 테스트셋 기준 |

---

## 10. 향후 통합 인터페이스 (Phase 4 준비)

현재 설계에서 향후 통합 시 변경이 필요한 접점:

| 통합 대상 | 현재 접점 | 통합 시 변경 |
|-----------|----------|------------|
| RAG Agent 실시간 | 별도 API 호출 | `rag_agent_router`에 BackgroundTask로 RealtimeEvalUseCase 연동 |
| Agent Builder 품질 게이트 | 없음 | `SupervisorConfig.quality_gate_enabled` → 평가 임계값 참조 |
| Hallucination 모듈 | 병렬 존재 | Faithfulness ≥ 0.8 → `is_hallucinated=False` 매핑 |
| 프론트엔드 대시보드 | REST API 제공 | `/api/ragas/runs`, `/runs/{id}` 그대로 사용 |
