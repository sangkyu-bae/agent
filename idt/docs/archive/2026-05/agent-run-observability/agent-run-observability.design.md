# Design: agent-run-observability

> Feature: Agent Run 운영 관측성 (Run/Step/Tool/Retrieval/LlmCall 영속화)
> Created: 2026-05-18
> Status: Design
> Depends-On: agent-run-observability.plan.md

---

## 0. 설계 개요 (Why this design)

- Plan에서 결정된 5개 신규 테이블(`ai_run`, `ai_run_step`, `ai_tool_call`, `ai_retrieval_source`, `ai_llm_call`) + `llm_model` 가격 컬럼 확장을 **Thin DDD** 레이어로 구체화한다.
- **핵심 설계 원칙 3가지**:
  1. **LLM 호출 수집은 단일 인터셉트 지점**(LangChain `BaseCallbackHandler`)에서만 발생 — 노드/툴/요약기/리랭커 코드를 흩뿌리지 않는다.
  2. **Best-effort 영속화** — 관측성 기록 실패가 본 흐름(사용자 응답)을 차단하지 않는다.
  3. **집계 성능은 비정규화로 확보** — `ai_llm_call`에 `user_id` / `agent_id` / `model_name` / `provider` 복제. 집계는 JOIN 없이 단일 테이블 스캔.

---

## 1. 레이어별 파일 구조

```
src/
├── domain/
│   └── agent_run/                            # 신규 도메인
│       ├── __init__.py
│       ├── entities.py                       # AgentRun, AgentRunStep, ToolCall, RetrievalSource, LlmCall
│       ├── value_objects.py                  # RunId, RunStatus, NodeType, RunPurpose, TokenUsage, CostUsd, MoneyDecimal
│       ├── interfaces.py                     # AgentRunRepositoryInterface, LlmCallRepositoryInterface
│       └── policies.py                       # RunStatusTransitionPolicy, CostCalculationPolicy
│
├── application/
│   └── agent_run/                            # 신규 유즈케이스/파사드
│       ├── __init__.py
│       ├── tracker.py                        # RunTracker (start/complete/fail/record_step/record_tool/record_retrieval/record_llm_call)
│       ├── cost_calculator.py                # CostCalculator (TTL 캐시) + RunObservabilityConfig
│       ├── context.py                        # RunContext ContextVar (§14-2 ★)
│       ├── aggregator.py                     # UsageAggregator (사용자별/LLM별/기간별)
│       ├── model_name_resolver.py            # LangChain model_name → llm_model.id 매핑
│       └── schemas.py                        # RunDetail / UserUsage / LlmUsage DTO
│
├── infrastructure/
│   ├── persistence/
│   │   ├── models/
│   │   │   └── agent_run.py                  # ORM: 5개 모델
│   │   └── repositories/
│   │       ├── agent_run_repository.py       # AgentRunRepositoryInterface 구현
│   │       └── llm_call_repository.py        # LlmCallRepositoryInterface (집계 쿼리 포함)
│   ├── llm/
│   │   └── usage_callback.py                 # UsageCallback (LangChain BaseCallbackHandler) ★ 핵심
│   └── langsmith/
│       └── trace_extractor.py                # LangSmith trace_id 추출 헬퍼
│
├── api/
│   ├── routes/
│   │   ├── agent_run_router.py               # GET /agents/runs/{run_id}
│   │   └── usage_router.py                   # /admin/usage/* + /usage/me
│   └── schemas/
│       └── agent_run.py                      # Pydantic 응답 스키마
│
└── db/migration/
    ├── V021__create_agent_run_tables.sql     # 5개 신규 테이블
    └── V022__add_llm_model_pricing.sql       # llm_model 가격 컬럼
```

---

## 2. Domain Layer

### 2-1. `src/domain/agent_run/value_objects.py`

```python
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


@dataclass(frozen=True)
class RunId:
    value: str  # UUID4

    def __post_init__(self) -> None:
        if not self.value or len(self.value) != 36:
            raise ValueError("RunId must be a UUID string")


class RunStatus(str, Enum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepStatus(str, Enum):
    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class NodeType(str, Enum):
    SUPERVISOR = "SUPERVISOR"
    WORKER = "WORKER"
    GATE = "GATE"
    OTHER = "OTHER"


class RunPurpose(str, Enum):
    """LLM 호출이 어떤 목적으로 발생했는지 (ai_llm_call.purpose)"""
    SUPERVISOR = "supervisor"
    WORKER = "worker"
    SUMMARIZER = "summarizer"
    QUERY_REWRITE = "query_rewrite"
    RERANK = "rerank"
    HALLUCINATION_CHECK = "hallucination_check"
    OTHER = "other"


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __post_init__(self) -> None:
        if self.prompt_tokens < 0 or self.completion_tokens < 0 or self.total_tokens < 0:
            raise ValueError("Token counts must be non-negative")

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


@dataclass(frozen=True)
class CostUsd:
    """USD 비용. 정밀도 6자리(DECIMAL(12,6))."""
    input_usd: Decimal = Decimal("0")
    output_usd: Decimal = Decimal("0")
    total_usd: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.input_usd < 0 or self.output_usd < 0 or self.total_usd < 0:
            raise ValueError("Cost must be non-negative")

    def __add__(self, other: "CostUsd") -> "CostUsd":
        return CostUsd(
            input_usd=self.input_usd + other.input_usd,
            output_usd=self.output_usd + other.output_usd,
            total_usd=self.total_usd + other.total_usd,
        )
```

### 2-2. `src/domain/agent_run/entities.py`

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from src.domain.agent_run.value_objects import (
    CostUsd,
    NodeType,
    RunId,
    RunPurpose,
    RunStatus,
    StepStatus,
    TokenUsage,
)


@dataclass
class AgentRun:
    id: RunId
    conversation_id: str
    user_id: str
    agent_id: str
    llm_model_id: Optional[str]              # Agent 주력 LLM
    user_message_id: Optional[int]
    status: RunStatus
    langgraph_thread_id: str
    langsmith_trace_id: Optional[str]
    langsmith_run_url: Optional[str]
    token_usage: TokenUsage                  # SUM(ai_llm_call.*)
    cost_usd: CostUsd                        # SUM(ai_llm_call.*)
    llm_call_count: int
    started_at: datetime
    ended_at: Optional[datetime]
    latency_ms: Optional[int]
    error_message: Optional[str]
    error_stack: Optional[str]


@dataclass
class AgentRunStep:
    id: str
    run_id: RunId
    step_index: int
    node_name: str
    node_type: NodeType
    llm_model_id: Optional[str]
    status: StepStatus
    input_summary: Optional[str]
    output_summary: Optional[str]
    started_at: datetime
    ended_at: Optional[datetime]
    latency_ms: Optional[int]
    error_text: Optional[str]


@dataclass
class ToolCall:
    id: str
    run_id: RunId
    step_id: Optional[str]
    tool_name: str
    llm_model_id: Optional[str]              # 툴 내부 LLM
    arguments_json: Optional[dict]
    result_summary: Optional[str]
    result_json: Optional[dict]
    token_usage: Optional[TokenUsage]
    total_cost_usd: Optional[Decimal]
    latency_ms: Optional[int]
    status: str                              # SUCCESS / FAILED
    error_text: Optional[str]
    created_at: datetime


@dataclass
class RetrievalSource:
    id: str
    run_id: RunId
    tool_call_id: Optional[str]
    collection_name: str
    document_id: Optional[str]
    chunk_id: Optional[str]
    score: Optional[float]
    rank_index: Optional[int]
    content_preview: Optional[str]
    metadata_json: Optional[dict]
    created_at: datetime


@dataclass
class LlmCall:
    """LLM API 호출 1건. 사용자별·LLM별 집계의 기준 단위."""
    id: str
    run_id: RunId
    step_id: Optional[str]
    tool_call_id: Optional[str]
    user_id: str                             # 비정규화 (집계 성능)
    agent_id: str                            # 비정규화
    llm_model_id: Optional[str]              # 매핑 실패 시 NULL
    provider: str                            # openai/anthropic/ollama/...
    model_name: str                          # 호출 시점 스냅샷 (gpt-4o 등)
    purpose: Optional[RunPurpose]
    token_usage: TokenUsage
    input_price_per_1k_usd: Optional[Decimal]   # 호출 시점 가격 스냅샷
    output_price_per_1k_usd: Optional[Decimal]
    cost_usd: CostUsd
    latency_ms: Optional[int]
    status: str                              # SUCCESS / FAILED
    error_text: Optional[str]
    created_at: datetime
```

### 2-3. `src/domain/agent_run/policies.py`

```python
from decimal import Decimal
from typing import Optional

from src.domain.agent_run.value_objects import CostUsd, RunStatus, TokenUsage


class RunStatusTransitionPolicy:
    """Run 상태 전이 규칙: RUNNING -> SUCCESS/FAILED/CANCELLED 만 허용."""

    _ALLOWED = {
        RunStatus.RUNNING: {RunStatus.SUCCESS, RunStatus.FAILED, RunStatus.CANCELLED},
        RunStatus.SUCCESS: set(),
        RunStatus.FAILED: set(),
        RunStatus.CANCELLED: set(),
    }

    @classmethod
    def can_transition(cls, current: RunStatus, target: RunStatus) -> bool:
        return target in cls._ALLOWED.get(current, set())

    @classmethod
    def ensure(cls, current: RunStatus, target: RunStatus) -> None:
        if not cls.can_transition(current, target):
            raise ValueError(f"Invalid run status transition: {current} -> {target}")


class CostCalculationPolicy:
    """가격 스냅샷 × 토큰 -> CostUsd. 가격이 None이면 0 비용."""

    @staticmethod
    def compute(
        token_usage: TokenUsage,
        input_price_per_1k_usd: Optional[Decimal],
        output_price_per_1k_usd: Optional[Decimal],
    ) -> CostUsd:
        if input_price_per_1k_usd is None or output_price_per_1k_usd is None:
            return CostUsd()
        input_usd = (Decimal(token_usage.prompt_tokens) / Decimal(1000)) * input_price_per_1k_usd
        output_usd = (Decimal(token_usage.completion_tokens) / Decimal(1000)) * output_price_per_1k_usd
        return CostUsd(
            input_usd=input_usd.quantize(Decimal("0.000001")),
            output_usd=output_usd.quantize(Decimal("0.000001")),
            total_usd=(input_usd + output_usd).quantize(Decimal("0.000001")),
        )
```

### 2-4. `src/domain/agent_run/interfaces.py`

```python
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from src.domain.agent_run.entities import (
    AgentRun,
    AgentRunStep,
    LlmCall,
    RetrievalSource,
    ToolCall,
)
from src.domain.agent_run.value_objects import RunId


class AgentRunRepositoryInterface(ABC):
    @abstractmethod
    async def save_run(self, run: AgentRun) -> AgentRun: ...

    @abstractmethod
    async def update_run(self, run: AgentRun) -> None: ...

    @abstractmethod
    async def find_run(self, run_id: RunId) -> Optional[AgentRun]: ...

    @abstractmethod
    async def save_step(self, step: AgentRunStep) -> AgentRunStep: ...

    @abstractmethod
    async def update_step(self, step: AgentRunStep) -> None: ...

    @abstractmethod
    async def save_tool_call(self, call: ToolCall) -> ToolCall: ...

    @abstractmethod
    async def save_retrieval(self, source: RetrievalSource) -> RetrievalSource: ...

    @abstractmethod
    async def find_steps(self, run_id: RunId) -> List[AgentRunStep]: ...

    @abstractmethod
    async def find_tool_calls(self, run_id: RunId) -> List[ToolCall]: ...

    @abstractmethod
    async def find_retrievals(self, run_id: RunId) -> List[RetrievalSource]: ...


class LlmCallRepositoryInterface(ABC):
    @abstractmethod
    async def save(self, call: LlmCall) -> LlmCall: ...

    @abstractmethod
    async def find_by_run(self, run_id: RunId) -> List[LlmCall]: ...

    @abstractmethod
    async def aggregate_by_user(
        self, from_dt: datetime, to_dt: datetime
    ) -> List["UserUsageRow"]: ...

    @abstractmethod
    async def aggregate_by_llm_model(
        self, from_dt: datetime, to_dt: datetime
    ) -> List["LlmUsageRow"]: ...

    @abstractmethod
    async def aggregate_user_x_llm(
        self, user_id: str, from_dt: datetime, to_dt: datetime
    ) -> List["LlmUsageRow"]: ...
```

---

## 3. Application Layer

### 3-1. `src/application/agent_run/tracker.py`

**의존성 주입:**
- `run_repo: AgentRunRepositoryInterface`
- `llm_call_repo: LlmCallRepositoryInterface`
- `cost_calculator: CostCalculator`
- `model_name_resolver: ModelNameResolver`
- `logger: LoggerInterface`

**핵심 API:**

```python
class RunTracker:
    async def start_run(
        self,
        conversation_id: str,
        user_id: str,
        agent_id: str,
        agent_llm_model_id: Optional[str],
        user_message_id: Optional[int],
        langgraph_thread_id: str,
    ) -> RunId:
        """ai_run row 즉시 INSERT (status=RUNNING). 실패 시 RuntimeError raise."""

    async def complete_run(
        self,
        run_id: RunId,
        langsmith_trace_id: Optional[str] = None,
        langsmith_run_url: Optional[str] = None,
    ) -> None:
        """status=SUCCESS + SUM(ai_llm_call.*) → ai_run 합계 UPDATE.

        구현 (§14-5 확정):
            UPDATE ai_run SET
                prompt_tokens = COALESCE((SELECT SUM(prompt_tokens) FROM ai_llm_call WHERE run_id = :rid), 0),
                completion_tokens = COALESCE((SELECT SUM(completion_tokens) FROM ai_llm_call WHERE run_id = :rid), 0),
                total_tokens = COALESCE((SELECT SUM(total_tokens) FROM ai_llm_call WHERE run_id = :rid), 0),
                total_cost_usd = COALESCE((SELECT SUM(total_cost_usd) FROM ai_llm_call WHERE run_id = :rid), 0),
                llm_call_count = (SELECT COUNT(*) FROM ai_llm_call WHERE run_id = :rid),
                status = 'SUCCESS',
                ended_at = NOW(),
                langsmith_trace_id = :trace_id,
                langsmith_run_url = :run_url,
                latency_ms = TIMESTAMPDIFF(MICROSECOND, started_at, NOW()) / 1000
            WHERE id = :rid AND status = 'RUNNING';

        실패는 warning log만 (raise X).
        """

    async def fail_run(self, run_id: RunId, exception: BaseException) -> None:
        """status=FAILED + error_message/stack 기록. 실패는 로그만 (raise 안함)."""

    async def record_step(
        self,
        run_id: RunId,
        step_index: int,
        node_name: str,
        node_type: NodeType,
        llm_model_id: Optional[str],
        status: StepStatus,
        input_summary: Optional[str] = None,
        output_summary: Optional[str] = None,
        error_text: Optional[str] = None,
    ) -> str:  # returns step_id
        """노드 실행 기록. best-effort (실패해도 본 흐름 차단 X)."""

    async def record_tool_call(
        self,
        run_id: RunId,
        step_id: Optional[str],
        tool_name: str,
        arguments: Optional[dict],
        result_summary: Optional[str],
        latency_ms: Optional[int],
        status: str,
        llm_model_id: Optional[str] = None,
        error_text: Optional[str] = None,
    ) -> str:  # returns tool_call_id

    async def record_retrieval(
        self,
        run_id: RunId,
        tool_call_id: Optional[str],
        collection_name: str,
        document_id: Optional[str],
        chunk_id: Optional[str],
        score: Optional[float],
        rank_index: Optional[int],
        content_preview: Optional[str],
        metadata: Optional[dict] = None,
    ) -> None:

    async def record_llm_call(
        self,
        run_id: RunId,
        step_id: Optional[str],
        tool_call_id: Optional[str],
        user_id: str,
        agent_id: str,
        provider: str,
        model_name: str,
        purpose: Optional[RunPurpose],
        token_usage: TokenUsage,
        latency_ms: Optional[int],
        status: str,
        error_text: Optional[str] = None,
    ) -> None:
        """UsageCallback에서 호출. model_name -> llm_model_id 매핑 + 가격 조회 + 비용 계산 + INSERT."""
```

**Best-effort 정책 (Tracker 공통):**
```python
async def _safe(self, coro):
    try:
        return await coro
    except Exception as e:
        self._logger.warning("Tracker best-effort write failed", exception=e)
        return None
```

### 3-2. `src/application/agent_run/cost_calculator.py`

```python
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class RunObservabilityConfig:
    """관측성 모듈 설정 (config로 분리, 하드코딩 금지)."""
    pricing_cache_ttl_seconds: int = 300                  # 가격 캐시 TTL
    summary_text_max_bytes: int = 1024                    # input/output_summary 컷오프
    retrieval_preview_max_bytes: int = 500
    best_effort_log_level: str = "warning"


class CostCalculator:
    """llm_model 가격 컬럼을 TTL 캐싱하여 호출 시점 가격 스냅샷을 제공.

    TTL 기본 5분 — 가격 변동이 운영 중 발생하더라도 최대 5분 지연 후 반영.
    """

    def __init__(
        self,
        llm_model_repo: "LlmModelRepositoryInterface",
        config: RunObservabilityConfig,
    ):
        self._repo = llm_model_repo
        self._ttl = config.pricing_cache_ttl_seconds
        # cache: llm_model_id -> ((input_price, output_price), expires_at_ts)
        self._cache: dict[str, tuple[tuple[Optional[Decimal], Optional[Decimal]], float]] = {}

    async def get_pricing(
        self, llm_model_id: str
    ) -> tuple[Optional[Decimal], Optional[Decimal]]:
        now = time.monotonic()
        cached = self._cache.get(llm_model_id)
        if cached is not None and cached[1] > now:
            return cached[0]
        model = await self._repo.find_by_id(llm_model_id, request_id="cost-calc")
        if model is None:
            result = (None, None)
        else:
            result = (model.input_price_per_1k_usd, model.output_price_per_1k_usd)
        self._cache[llm_model_id] = (result, now + self._ttl)
        return result

    def invalidate(self, llm_model_id: Optional[str] = None) -> None:
        """관리자 가격 변경 API에서 호출 (PATCH /llm-models/{id}/pricing)."""
        if llm_model_id is None:
            self._cache.clear()
        else:
            self._cache.pop(llm_model_id, None)

    def compute(
        self,
        token_usage: TokenUsage,
        input_price: Optional[Decimal],
        output_price: Optional[Decimal],
    ) -> CostUsd:
        return CostCalculationPolicy.compute(token_usage, input_price, output_price)
```

> **캐시 무효화 정책 (확정 §14-6)**:
> - **수동 무효화**: 관리자 가격 변경 API(`PATCH /llm-models/{id}/pricing`)에서 `cost_calculator.invalidate(llm_model_id)` 호출 의무.
> - **TTL 만료**: 5분 후 다음 조회 시 자동 재로드.
> - **후속 확장**: `llm-pricing-sync` Plan에서 Redis pub/sub 기반 push invalidation으로 다중 워커 환경 대응.

### 3-2-1. `src/application/agent_run/context.py` ★ 신규 (§14-2 ContextVar 채택)

```python
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional

from src.domain.agent_run.value_objects import RunId


@dataclass(frozen=True)
class RunContext:
    """현재 활성 LangGraph run의 컨텍스트.

    LangGraph 외부에서 호출되는 RAG 어댑터·Summarizer·외부 툴이 이 ContextVar에서
    run_id / step_id / tool_call_id를 읽어 tracker.record_retrieval() 등을 호출한다.
    """
    run_id: RunId
    user_id: str
    agent_id: str
    callback: "UsageCallback"        # purpose/step/tool setter 호출용
    step_id: Optional[str] = None
    tool_call_id: Optional[str] = None


_current_run_context: ContextVar[Optional[RunContext]] = ContextVar(
    "_current_run_context", default=None
)


def get_current_run_context() -> Optional[RunContext]:
    return _current_run_context.get()


def set_current_run_context(ctx: Optional[RunContext]) -> "Token":
    return _current_run_context.set(ctx)


def reset_run_context(token: "Token") -> None:
    _current_run_context.reset(token)
```

**사용 패턴 (RunAgentUseCase 진입 시):**
```python
token = set_current_run_context(RunContext(run_id, user_id, agent_id, callback))
try:
    await graph.ainvoke(initial_state, config=config)
finally:
    reset_run_context(token)
```

**RAG 어댑터에서 사용:**
```python
async def retrieve_chunks(query: str) -> list[Chunk]:
    chunks = await self._retriever.retrieve(query)
    ctx = get_current_run_context()
    if ctx is not None:
        for rank, c in enumerate(chunks):
            await self._tracker.record_retrieval(
                run_id=ctx.run_id,
                tool_call_id=ctx.tool_call_id,
                collection_name=c.collection,
                document_id=c.doc_id, chunk_id=c.chunk_id,
                score=c.score, rank_index=rank,
                content_preview=c.content[:500],
            )
    return chunks
```

> **ContextVar 선택 이유**: asyncio Task별로 자동 격리 → 동시 다중 사용자 요청에서 컨텍스트 혼선 없음. LangChain callback config로는 RAG 어댑터까지 전파가 어려운 케이스를 커버.

### 3-3. `src/application/agent_run/model_name_resolver.py`

```python
class ModelNameResolver:
    """LangChain model_name 문자열 → llm_model.id 매핑.

    매핑 실패 시 NULL 반환 + warning log (이후 사후 매핑 가능).
    캐시는 (provider, model_name) -> Optional[llm_model_id].
    """

    def __init__(self, llm_model_repo: LlmModelRepositoryInterface, logger: LoggerInterface):
        self._repo = llm_model_repo
        self._logger = logger
        self._cache: dict[tuple[str, str], Optional[str]] = {}

    async def resolve(self, provider: str, model_name: str) -> Optional[str]:
        key = (provider, model_name)
        if key in self._cache:
            return self._cache[key]
        models = await self._repo.find_by_provider_and_name(provider, model_name)
        result = models.id if models else None
        if result is None:
            self._logger.warning(
                "LLM model not registered",
                provider=provider,
                model_name=model_name,
            )
        self._cache[key] = result
        return result
```

> `LlmModelRepositoryInterface.find_by_provider_and_name()` 신규 메서드는 기존 unique index `uq_provider_model`을 활용. M1에서 추가.

### 3-4. `src/application/agent_run/aggregator.py`

```python
@dataclass
class UserUsageRow:
    user_id: str
    total_tokens: int
    total_cost_usd: Decimal
    call_count: int


@dataclass
class LlmUsageRow:
    llm_model_id: Optional[str]
    provider: str
    model_name: str
    total_tokens: int
    total_cost_usd: Decimal
    call_count: int


class UsageAggregator:
    def __init__(self, llm_call_repo: LlmCallRepositoryInterface):
        self._repo = llm_call_repo

    async def by_user(self, from_dt: datetime, to_dt: datetime) -> List[UserUsageRow]: ...
    async def by_llm_model(self, from_dt: datetime, to_dt: datetime) -> List[LlmUsageRow]: ...
    async def for_user(self, user_id: str, from_dt: datetime, to_dt: datetime) -> List[LlmUsageRow]: ...
```

---

## 4. Infrastructure Layer

### 4-1. `src/infrastructure/persistence/models/agent_run.py` (ORM 핵심 발췌)

```python
class AgentRunModel(Base):
    __tablename__ = "ai_run"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False)
    llm_model_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    user_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    langgraph_thread_id: Mapped[str] = mapped_column(String(150), nullable=False)
    langsmith_trace_id: Mapped[Optional[str]] = mapped_column(String(150))
    langsmith_run_url: Mapped[Optional[str]] = mapped_column(String(500))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0, nullable=False)
    llm_call_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    error_stack: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        Index("idx_run_conversation", "conversation_id"),
        Index("idx_run_agent", "agent_id"),
        Index("idx_run_user_started", "user_id", "started_at"),
        Index("idx_run_llm_model", "llm_model_id"),
        Index("idx_run_status", "status"),
        Index("idx_run_started_at", "started_at"),
    )


class LlmCallModel(Base):
    __tablename__ = "ai_llm_call"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    step_id: Mapped[Optional[str]] = mapped_column(String(36))
    tool_call_id: Mapped[Optional[str]] = mapped_column(String(36))
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False)
    llm_model_id: Mapped[Optional[str]] = mapped_column(String(36))
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(150), nullable=False)
    purpose: Mapped[Optional[str]] = mapped_column(String(50))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_price_per_1k_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    output_price_per_1k_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    input_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0, nullable=False)
    output_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0, nullable=False)
    total_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0, nullable=False)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_text: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("idx_llm_call_user_created", "user_id", "created_at"),
        Index("idx_llm_call_model_created", "llm_model_id", "created_at"),
        Index("idx_llm_call_user_model", "user_id", "llm_model_id"),
        Index("idx_llm_call_agent", "agent_id"),
        Index("idx_llm_call_run", "run_id"),
    )
```

> 나머지 ORM(`AgentRunStepModel`, `ToolCallModel`, `RetrievalSourceModel`)은 Plan §5 SQL과 1:1 대응.

### 4-2. `src/infrastructure/persistence/repositories/llm_call_repository.py`

집계 쿼리는 GROUP BY를 SQLAlchemy `func.sum/count`로 표현:

```python
class SqlAlchemyLlmCallRepository(LlmCallRepositoryInterface):
    async def aggregate_by_user(self, from_dt, to_dt) -> List[UserUsageRow]:
        async with self._session_factory() as session:
            stmt = (
                select(
                    LlmCallModel.user_id,
                    func.sum(LlmCallModel.total_tokens).label("tokens"),
                    func.sum(LlmCallModel.total_cost_usd).label("cost"),
                    func.count().label("calls"),
                )
                .where(LlmCallModel.created_at.between(from_dt, to_dt))
                .group_by(LlmCallModel.user_id)
            )
            rows = (await session.execute(stmt)).all()
            return [UserUsageRow(r.user_id, r.tokens, r.cost, r.calls) for r in rows]

    async def aggregate_by_llm_model(self, from_dt, to_dt) -> List[LlmUsageRow]:
        # 동일 패턴, group_by(llm_model_id, provider, model_name)
        ...
```

### 4-3. ★ `src/infrastructure/llm/usage_callback.py` (핵심 인터셉트)

```python
class UsageCallback(AsyncCallbackHandler):
    """LangChain 모든 LLM 호출 종료 시점에 토큰·비용 수집.

    Supervisor / Worker / Summarizer / Tool 내부 LLM 호출을 단일 지점에서 수집.
    """

    def __init__(
        self,
        tracker: RunTracker,
        run_id: RunId,
        user_id: str,
        agent_id: str,
        logger: LoggerInterface,
    ):
        self._tracker = tracker
        self._run_id = run_id
        self._user_id = user_id
        self._agent_id = agent_id
        self._logger = logger
        # 현재 활성 step / tool_call 컨텍스트 (LangGraph 노드 진입 시 set)
        self._current_step_id: Optional[str] = None
        self._current_tool_call_id: Optional[str] = None
        self._current_purpose: Optional[RunPurpose] = None
        self._start_ts: dict[uuid.UUID, float] = {}

    async def on_llm_start(self, serialized, prompts, *, run_id, **kwargs):
        self._start_ts[run_id] = time.monotonic()

    async def on_llm_end(self, response: LLMResult, *, run_id, **kwargs):
        latency_ms = int((time.monotonic() - self._start_ts.pop(run_id, time.monotonic())) * 1000)
        provider, model_name = self._extract_model(response, kwargs)
        token_usage = self._extract_tokens(response, provider)
        await self._tracker.record_llm_call(
            run_id=self._run_id,
            step_id=self._current_step_id,
            tool_call_id=self._current_tool_call_id,
            user_id=self._user_id,
            agent_id=self._agent_id,
            provider=provider,
            model_name=model_name,
            purpose=self._current_purpose,
            token_usage=token_usage,
            latency_ms=latency_ms,
            status="SUCCESS",
        )

    async def on_llm_error(self, error, *, run_id, **kwargs):
        latency_ms = int((time.monotonic() - self._start_ts.pop(run_id, time.monotonic())) * 1000)
        provider, model_name = self._extract_model_from_kwargs(kwargs)
        await self._tracker.record_llm_call(
            run_id=self._run_id,
            step_id=self._current_step_id,
            tool_call_id=self._current_tool_call_id,
            user_id=self._user_id,
            agent_id=self._agent_id,
            provider=provider,
            model_name=model_name,
            purpose=self._current_purpose,
            token_usage=TokenUsage(),
            latency_ms=latency_ms,
            status="FAILED",
            error_text=str(error),
        )

    # ── purpose / step / tool 컨텍스트 setter ──
    # §14-1 확정: 모든 노드/툴 진입 지점에서 set_purpose() 호출 의무.
    # purpose가 None이면 코드 누락 → record_llm_call에서 warning log 발생.
    def set_purpose(self, purpose: RunPurpose) -> None:
        self._current_purpose = purpose

    def enter_step(self, step_id: str) -> None:
        self._current_step_id = step_id

    def exit_step(self) -> None:
        self._current_step_id = None

    def enter_tool(self, tool_call_id: str) -> None:
        self._current_tool_call_id = tool_call_id

    def exit_tool(self) -> None:
        self._current_tool_call_id = None

    # ── Provider별 파싱 ──
    def _extract_model(self, response: LLMResult, kwargs: dict) -> tuple[str, str]:
        llm_output = response.llm_output or {}
        model_name = llm_output.get("model_name") or llm_output.get("model") or kwargs.get("invocation_params", {}).get("model", "unknown")
        provider = self._infer_provider(model_name, llm_output)
        return provider, model_name

    def _infer_provider(self, model_name: str, llm_output: dict) -> str:
        # 1) llm_output에 명시되어 있으면 사용
        if "provider" in llm_output:
            return llm_output["provider"]
        # 2) 모델명 prefix로 추정 (fallback)
        if model_name.startswith(("gpt-", "o1-", "o3-")):
            return "openai"
        if model_name.startswith("claude-"):
            return "anthropic"
        if model_name.startswith(("llama", "qwen", "mistral", "gemma")):
            return "ollama"
        return "unknown"

    def _extract_tokens(self, response: LLMResult, provider: str) -> TokenUsage:
        """Provider별 usage_metadata 형식 차이를 흡수."""
        token_usage_dict = self._collect_usage_from_response(response, provider)
        return TokenUsage(
            prompt_tokens=token_usage_dict.get("prompt", 0),
            completion_tokens=token_usage_dict.get("completion", 0),
            total_tokens=token_usage_dict.get("total", 0),
        )

    def _collect_usage_from_response(self, response: LLMResult, provider: str) -> dict:
        # LangChain 0.3+ 일관 키: response.llm_output["token_usage"]
        usage = (response.llm_output or {}).get("token_usage") or {}
        if not usage:
            # generation별 usage_metadata 합산 (Anthropic 등)
            usage = self._sum_generation_usage(response, provider)
        return self._normalize_keys(usage, provider)

    def _normalize_keys(self, usage: dict, provider: str) -> dict:
        """provider별 키 차이 정규화."""
        if provider == "openai":
            return {
                "prompt": usage.get("prompt_tokens", 0),
                "completion": usage.get("completion_tokens", 0),
                "total": usage.get("total_tokens", 0),
            }
        if provider == "anthropic":
            input_t = usage.get("input_tokens", 0)
            output_t = usage.get("output_tokens", 0)
            return {"prompt": input_t, "completion": output_t, "total": input_t + output_t}
        if provider == "ollama":
            prompt = usage.get("prompt_eval_count", 0)
            completion = usage.get("eval_count", 0)
            return {"prompt": prompt, "completion": completion, "total": prompt + completion}
        # 기본: openai 키로 시도
        return {
            "prompt": usage.get("prompt_tokens", 0),
            "completion": usage.get("completion_tokens", 0),
            "total": usage.get("total_tokens", 0),
        }
```

### 4-4. UsageCallback 생명주기 시퀀스

```
RunAgentUseCase.execute()
 │
 ├─ tracker.start_run() ──► INSERT ai_run (RUNNING)
 │
 ├─ callback = UsageCallback(tracker, run_id, user_id, agent_id, logger)
 │
 ├─ config["callbacks"] = [callback]
 ├─ config["metadata"] = {run_id, conversation_id, user_id, agent_id}
 │
 ├─ graph.ainvoke(initial_state, config)
 │   │
 │   ├─ supervisor_node:
 │   │   ├─ tracker.record_step(SUPERVISOR, STARTED) → step_id
 │   │   ├─ callback.enter_step(step_id)
 │   │   ├─ callback.set_purpose(SUPERVISOR)
 │   │   ├─ llm.with_structured_output(SupervisorDecision).ainvoke(msgs)
 │   │   │   └─ ★ callback.on_llm_end() ─► tracker.record_llm_call(purpose=supervisor)
 │   │   ├─ callback.exit_step()
 │   │   └─ tracker.update_step(SUCCESS, output_summary)
 │   │
 │   ├─ worker_node:
 │   │   ├─ tracker.record_step(WORKER, STARTED) → step_id
 │   │   ├─ callback.enter_step(step_id); set_purpose(WORKER)
 │   │   │   (worker가 tool을 호출하면)
 │   │   │   ├─ tracker.record_tool_call(STARTED) → tool_call_id
 │   │   │   ├─ callback.enter_tool(tool_call_id)
 │   │   │   ├─ tool 실행 → 내부 LLM 호출 시 callback.on_llm_end()
 │   │   │   ├─ callback.exit_tool()
 │   │   │   └─ tracker.update_tool_call(SUCCESS, result_summary, latency)
 │   │   ├─ worker 자체의 llm.ainvoke() → callback.on_llm_end()
 │   │   ├─ callback.exit_step()
 │   │   └─ tracker.update_step(SUCCESS)
 │   │
 │   └─ (반복)
 │
 ├─ langsmith_trace_id = TraceExtractor.extract()
 ├─ tracker.complete_run(run_id, langsmith_trace_id, run_url)
 │   ├─ SUM(ai_llm_call.* WHERE run_id) → ai_run 합계 갱신
 │   └─ UPDATE ai_run SET status=SUCCESS, ended_at=now
 │
 └─ (예외 시) tracker.fail_run(run_id, exc)
```

### 4-5. `src/infrastructure/langsmith/trace_extractor.py`

```python
from langsmith.run_helpers import get_current_run_tree

class TraceExtractor:
    """현재 LangSmith run의 trace_id / run_url을 회수."""

    @staticmethod
    def extract() -> tuple[Optional[str], Optional[str]]:
        try:
            tree = get_current_run_tree()
            if tree is None:
                return (None, None)
            trace_id = str(tree.trace_id) if tree.trace_id else None
            run_url = tree.url if hasattr(tree, "url") else None
            return (trace_id, run_url)
        except Exception:
            return (None, None)
```

---

## 5. 기존 코드 통합 지점

### 5-1. `src/application/agent_builder/run_agent_use_case.py`

**변경 요점:**

```python
class RunAgentUseCase:
    def __init__(
        self,
        ...
        tracker: RunTracker,                      # ★ 신규
    ): ...

    async def execute(self, agent_id, request, request_id, viewer_user_id, ...):
        langsmith(project_name="agent-run")
        run_id_str = str(uuid.uuid4())
        run_id = RunId(run_id_str)

        # ── 1) Run 시작 (즉시 INSERT) ──
        await self._tracker.start_run(
            run_id=run_id,
            conversation_id=session_id,
            user_id=request.user_id,
            agent_id=agent_id,
            agent_llm_model_id=agent.llm_model_id,
            user_message_id=None,                 # 메시지 저장 전이므로 None
            langgraph_thread_id=session_id,
        )

        # ── 2) UsageCallback 등록 ──
        callback = UsageCallback(self._tracker, run_id, request.user_id, agent_id, self._logger)

        config = {
            "configurable": {"thread_id": session_id},
            "metadata": {
                "run_id": run_id_str,
                "conversation_id": session_id,
                "user_id": request.user_id,
                "agent_id": agent_id,
            },
            "tags": ["agent-platform", agent_id, "production"],
            "callbacks": [callback],
        }

        # ── 2-1) ContextVar 설정 (§14-2 확정) ──
        ctx_token = set_current_run_context(RunContext(
            run_id=run_id,
            user_id=request.user_id,
            agent_id=agent_id,
            callback=callback,
        ))

        try:
            ...
            result = await graph.ainvoke(initial_state, config=config)
            answer, tools_used = self._parse_result(result)

            # ── 3) 메시지 저장 (기존 로직) ──
            await self._save_turn(request.query, answer, request.user_id, session_id, agent_id)

            # ── 4) trace_id 회수 + Run 완료 (§14-4 확정) ──
            trace_id, run_url = TraceExtractor.extract()
            await self._tracker.complete_run(run_id, trace_id, run_url)

            return RunAgentResponse(
                ...,
                run_id=run_id_str,                # ★ 응답에 노출
            )
        except Exception as e:
            await self._tracker.fail_run(run_id, e)
            raise
        finally:
            reset_run_context(ctx_token)
```

**주의:**
- `_save_turn` 내부에서 user_message_id를 얻은 뒤 `tracker.update_run(user_message_id=...)` 한 번 더 호출 (또는 user_message 저장을 run 시작 전으로 옮기는 안 — 후자가 깔끔하므로 채택, 아래 5-2 참조).
- `langsmith_trace_id` 회수가 실패해도 complete_run은 그대로 진행 (nullable).

### 5-2. user_message 저장 순서 변경

**현재**: graph 실행 후 `_save_turn`에서 user/assistant 동시 저장.
**변경**: user_message는 run 시작 **전**에 저장, assistant_message는 graph 종료 후.

```
1. user_message 저장 → message_id 회수
2. tracker.start_run(user_message_id=message_id, ...)
3. graph 실행
4. assistant_message 저장
5. tracker.complete_run(...)
```

이유: 중간에 graph가 죽어도 "이 사용자가 무엇을 물었는지" + "어떤 run이 실패했는지"가 정합성 있게 남는다.

### 5-3. `src/application/agent_builder/supervisor_nodes.py`

```python
def create_supervisor_node(llm, workers, supervisor_prompt, hooks, logger, tracker, callback):
    async def supervisor_node(state: SupervisorState) -> dict:
        run_id = RunId(state["run_id"])              # ★ state에 run_id 추가
        step_id = await tracker.record_step(
            run_id=run_id,
            step_index=state["iteration_count"],
            node_name="supervisor",
            node_type=NodeType.SUPERVISOR,
            llm_model_id=state.get("supervisor_llm_model_id"),
            status=StepStatus.STARTED,
        )
        callback.enter_step(step_id)
        callback.set_purpose(RunPurpose.SUPERVISOR)       # §14-1 확정: 노드 진입 시 명시
        try:
            decision = await llm.with_structured_output(SupervisorDecision).ainvoke(...)
            await tracker.update_step(step_id, status=StepStatus.SUCCESS,
                                      output_summary=decision.reasoning[:1024])
            return {...}
        except Exception as e:
            await tracker.update_step(step_id, status=StepStatus.FAILED, error_text=str(e))
            raise
        finally:
            callback.exit_step()
```

**state에 추가할 키**:
- `run_id: str`
- `supervisor_llm_model_id: Optional[str]`
- `worker_llm_model_ids: dict[str, Optional[str]]`

이 키들은 `build_initial_state()`에서 채운다.

### 5-4. `src/application/agent_builder/workflow_compiler.py`

WorkflowCompiler가 worker별 `LlmModel`을 알고 있으므로, `worker_id → llm_model_id` 매핑을 `SupervisorState`에 주입한다. 컴파일 시점에 결정 가능.

### 5-5. `src/application/rag_agent/tools.py` 등 RAG 툴 (§14-2 ContextVar 채택)

RAG 툴이 검색 결과를 반환하는 시점에 `get_current_run_context()`로 컨텍스트를 읽어 `tracker.record_retrieval()` 호출:

```python
from src.application.agent_run.context import get_current_run_context

async def _rag_search_tool_impl(query: str, ...):
    documents = await retriever.retrieve(query, top_k=...)
    ctx = get_current_run_context()
    if ctx is not None:                                  # graph 외부 호출이면 None
        for rank, doc in enumerate(documents):
            await tracker.record_retrieval(
                run_id=ctx.run_id,
                tool_call_id=ctx.tool_call_id,           # 현재 활성 tool_call (없으면 None)
                collection_name=collection,
                document_id=doc.id,
                chunk_id=doc.chunk_id,
                score=doc.score,
                rank_index=rank,
                content_preview=doc.content[:500],
                metadata=doc.metadata,
            )
    return documents
```

**Tool 진입 시 ContextVar 갱신** — WorkflowCompiler에서 tool wrapper로 감싸서:
```python
async def _wrapped_tool_call(tool_fn, args, **kw):
    ctx = get_current_run_context()
    tool_call_id = await tracker.record_tool_call(
        run_id=ctx.run_id, step_id=ctx.step_id,
        tool_name=tool_fn.name, arguments=args,
        result_summary=None, latency_ms=None, status="STARTED",
    )
    new_ctx = replace(ctx, tool_call_id=tool_call_id)
    token = set_current_run_context(new_ctx)
    ctx.callback.enter_tool(tool_call_id)
    ctx.callback.set_purpose(_infer_tool_purpose(tool_fn.name))  # §14-1 확정: 진입 시 명시
    try:
        result = await tool_fn(args, **kw)
        await tracker.update_tool_call(tool_call_id, status="SUCCESS",
                                       result_summary=str(result)[:1024])
        return result
    except Exception as e:
        await tracker.update_tool_call(tool_call_id, status="FAILED", error_text=str(e))
        raise
    finally:
        ctx.callback.exit_tool()
        reset_run_context(token)
```

**`_infer_tool_purpose()` 매핑 표** (§14-1 노드/툴 진입 시 명시):

| tool_name 패턴 | RunPurpose |
|---------------|-----------|
| `rag_search`, `retrieval_*`, `hybrid_search` | `WORKER` (도구 호출자 관점) — 단, 툴 내부에서 query_rewrite/rerank LLM 호출 시 callback이 진입 시점에 `set_purpose(QUERY_REWRITE/RERANK)`로 덮어씀 |
| `query_rewriter_*` | `QUERY_REWRITE` |
| `reranker_*`, `compressor_*` | `RERANK` |
| `hallucination_*` | `HALLUCINATION_CHECK` |
| 그 외 | `OTHER` |

### 5-5-1. `src/infrastructure/llm/llm_factory.py` — `stream_usage=True` 일괄 적용 (§14-3 확정)

streaming 응답에서도 토큰 집계가 누락되지 않도록 LLMFactory가 provider별로 일괄 설정:

```python
class LLMFactory(LLMFactoryInterface):
    def _create_openai(self, llm_model, temperature) -> ChatOpenAI:
        return ChatOpenAI(
            model=llm_model.model_name,
            api_key=self._resolve_api_key(llm_model),
            temperature=temperature,
            stream_usage=True,                # ★ M1 추가 (streaming 시 usage_metadata 보장)
        )

    def _create_anthropic(self, llm_model, temperature) -> ChatAnthropic:
        return ChatAnthropic(
            model=llm_model.model_name,
            api_key=self._resolve_api_key(llm_model),
            temperature=temperature,
            # Anthropic은 streaming usage가 기본 포함 (별도 옵션 불필요)
        )

    def _create_ollama(self, llm_model, temperature) -> ChatOllama:
        return ChatOllama(
            model=llm_model.model_name,
            temperature=temperature,
            # Ollama는 응답 자체에 prompt_eval_count/eval_count 포함
        )
```

**검증 테스트** (M1 필수):
- OpenAI streaming 응답에서 `response.usage_metadata`가 마지막 청크에 존재
- Anthropic streaming 응답에서 `input_tokens` / `output_tokens` 수집
- Ollama streaming 응답에서 `prompt_eval_count` / `eval_count` 수집

### 5-6. Summarizer (`ConversationSummarizerInterface`)

§14-2 ContextVar 채택으로 callback 전달이 자동화됨:

```python
async def summarize(self, messages, session_id):
    ctx = get_current_run_context()
    callbacks = [ctx.callback] if ctx else []
    if ctx is not None:
        ctx.callback.set_purpose(RunPurpose.SUMMARIZER)   # §14-1 확정
    result = await self._llm.ainvoke(
        prompt, config={"callbacks": callbacks}
    )
    return result.content
```

Summarizer가 graph 외부에서 호출되더라도 ContextVar로 동일하게 동작.

---

## 6. API Layer

### 6-1. `src/api/routes/agent_run_router.py`

```python
@router.get("/agents/runs/{run_id}", response_model=RunDetailResponse)
async def get_run_detail(
    run_id: str,
    user: AuthUser = Depends(get_current_user),
    use_case: GetRunDetailUseCase = Depends(),
):
    return await use_case.execute(run_id, viewer_user_id=user.id, viewer_role=user.role)
```

**RunDetailResponse**:
```python
class RunDetailResponse(BaseModel):
    run: RunSummary                         # ai_run row
    steps: List[StepItem]
    tool_calls: List[ToolCallItem]
    retrievals: List[RetrievalItem]
    llm_calls: List[LlmCallItem]
    langsmith_run_url: Optional[str]
```

**권한**: 본인 run만 조회 (admin은 모두). `viewer_user_id == run.user_id or viewer_role == "admin"`.

### 6-2. `src/api/routes/usage_router.py`

```python
# 관리자: 사용자별 집계
@router.get("/admin/usage/users", response_model=List[UserUsageItem])
async def list_user_usage(
    from_: date = Query(alias="from"),
    to: date = Query(),
    _admin: AuthUser = Depends(require_admin),
    aggregator: UsageAggregator = Depends(),
):
    rows = await aggregator.by_user(datetime.combine(from_, time.min), datetime.combine(to, time.max))
    return [UserUsageItem.from_row(r) for r in rows]


# 관리자: LLM 모델별 집계
@router.get("/admin/usage/llm-models", response_model=List[LlmUsageItem])
async def list_llm_usage(...): ...


# 본인 마이페이지
@router.get("/usage/me", response_model=List[LlmUsageItem])
async def my_usage(
    from_: date = Query(alias="from"),
    to: date = Query(),
    user: AuthUser = Depends(get_current_user),
    aggregator: UsageAggregator = Depends(),
):
    return await aggregator.for_user(user.id, ...)
```

**페이지네이션**: M4 초기는 일/주/월 범위만 지원 (range가 큰 경우 클라이언트가 분할 호출). 향후 cursor-based 페이지네이션은 후속 PDCA.

---

## 7. main.py 변경사항 (DI)

```python
# lifespan 안에서 초기화 후 dependency_overrides로 주입
_run_tracker: Optional[RunTracker] = None
_usage_aggregator: Optional[UsageAggregator] = None

def create_run_tracker(session_factory, llm_model_repo, logger) -> RunTracker:
    run_repo = SqlAlchemyAgentRunRepository(session_factory)
    llm_call_repo = SqlAlchemyLlmCallRepository(session_factory)
    cost_calc = CostCalculator(llm_model_repo)
    model_resolver = ModelNameResolver(llm_model_repo, logger)
    return RunTracker(run_repo, llm_call_repo, cost_calc, model_resolver, logger)

# RunAgentUseCase factory에 tracker 주입
def create_run_agent_use_case(...):
    return RunAgentUseCase(..., tracker=_run_tracker)

# 라우터 등록
app.include_router(agent_run_router)
app.include_router(usage_router)
app.dependency_overrides[get_run_tracker] = lambda: _run_tracker
app.dependency_overrides[get_usage_aggregator] = lambda: _usage_aggregator
```

---

## 8. 마이그레이션 SQL (V021 / V022)

### V022__add_llm_model_pricing.sql (먼저 적용)

```sql
ALTER TABLE llm_model
    ADD COLUMN input_price_per_1k_usd  DECIMAL(10, 6) NULL COMMENT '입력 토큰 1000개당 USD',
    ADD COLUMN output_price_per_1k_usd DECIMAL(10, 6) NULL COMMENT '출력 토큰 1000개당 USD',
    ADD COLUMN pricing_updated_at      DATETIME       NULL;

-- 초기 가격 시드 (2026-05 기준, 운영팀이 주기적으로 갱신)
UPDATE llm_model SET
    input_price_per_1k_usd = 0.005,
    output_price_per_1k_usd = 0.015,
    pricing_updated_at = NOW()
WHERE provider = 'openai' AND model_name = 'gpt-4o';
-- (gpt-4o-mini, claude-3-5-sonnet 등은 운영팀 결정에 따라 추가 INSERT/UPDATE)
```

### V021__create_agent_run_tables.sql (V022 다음)

> 본 Design §2/4 SQL을 통합. Plan §5 의 5개 테이블 정의를 그대로 사용. (중복 명시 생략 — 마이그레이션 파일은 Plan SQL 1:1 복사.)

**중요 마이그레이션 순서:**
1. V022 (llm_model에 가격 컬럼 추가)
2. V021 (ai_run, ai_llm_call 등 5개 신규 테이블 — `ai_run.llm_model_id` FK 가능)

---

## 9. 테스트 설계

### 9-1. Domain

| 파일 | 케이스 |
|------|--------|
| `tests/domain/agent_run/test_value_objects.py` | TokenUsage 합산 / 음수 거부 / CostUsd 합산 / RunId 검증 |
| `tests/domain/agent_run/test_entities.py` | AgentRun / LlmCall 생성 / 필수 필드 검증 |
| `tests/domain/agent_run/test_policies.py` | RunStatusTransitionPolicy (RUNNING→SUCCESS 허용, SUCCESS→RUNNING 거부 등) / CostCalculationPolicy (가격 None → 0 비용, 정밀도 6자리 검증) |

### 9-2. Infrastructure

| 파일 | 케이스 |
|------|--------|
| `tests/infrastructure/agent_run/test_agent_run_repository.py` | save_run/update_run/find_run / step/tool/retrieval CRUD / FK CASCADE 동작 |
| `tests/infrastructure/agent_run/test_llm_call_repository.py` | save / find_by_run / **aggregate_by_user** (3 users × 2 days 데이터로 검증) / **aggregate_by_llm_model** / **aggregate_user_x_llm** |
| `tests/infrastructure/llm/test_usage_callback.py` | on_llm_end → record_llm_call 호출 / OpenAI usage_metadata 파싱 / Anthropic input_tokens→prompt_tokens 변환 / Ollama prompt_eval_count 변환 / 미인식 provider → unknown / on_llm_error 시 status=FAILED |

### 9-3. Application

| 파일 | 케이스 |
|------|--------|
| `tests/application/agent_run/test_run_tracker.py` | start_run / **complete_run의 SUM UPDATE 검증** (§14-5) / fail_run / record_step/tool/retrieval/llm_call best-effort (실패해도 raise 안됨) |
| `tests/application/agent_run/test_cost_calculator.py` | 가격 × 토큰 산출 정확도 / 가격 None 처리 / **TTL 캐시 만료 후 재로드 (§14-6)** / **invalidate() 동작** / mock clock으로 ttl 검증 |
| `tests/application/agent_run/test_context.py` | **ContextVar 격리 검증 (§14-2)**: 동시 asyncio task에서 컨텍스트 혼선 없음 / 외부 호출 시 None 반환 |
| `tests/application/agent_run/test_model_name_resolver.py` | 등록 모델 매핑 성공 / 미등록 모델 None + warning log |
| `tests/application/agent_run/test_aggregator.py` | by_user / by_llm_model / for_user 집계 정확도 |
| `tests/infrastructure/llm/test_llm_factory_stream_usage.py` | **§14-3 확정 검증**: OpenAI `stream_usage=True` 적용 / streaming 응답에서 토큰 메타데이터 수집 가능 |

### 9-4. Integration

| 파일 | 케이스 |
|------|--------|
| `tests/application/agent_builder/test_run_agent_use_case_observability.py` | execute 성공 시 ai_run row 생성 + status=SUCCESS / 실패 시 status=FAILED + error_message / 한 run에 supervisor + worker + summarizer 호출 시 ai_llm_call ≥ 3 row + 각 row의 llm_model_id 일관성 / ai_run.total_tokens == SUM(ai_llm_call.total_tokens) |
| `tests/api/test_agent_run_router.py` | 본인 run 조회 200 / 타인 run 조회 403 / admin은 타인 run 조회 200 |
| `tests/api/test_usage_router.py` | /admin/usage/users admin만 200 / /usage/me 본인 데이터만 / from-to 범위 필터링 |

**테스트 수**: 약 45개 (M1 기준 ~25개, M2 +5, M3 +5, M4 +10).

---

## 10. 로깅 (LOG-001)

```python
# Run lifecycle
logger.info("AgentRun started", run_id=run_id, user_id=user_id, agent_id=agent_id)
logger.info("AgentRun completed", run_id=run_id, latency_ms=ms, total_tokens=t, total_cost_usd=c)
logger.error("AgentRun failed", run_id=run_id, exception=e)

# LLM call
logger.info("LLM call recorded", run_id=run_id, provider=p, model=m, prompt=pt, completion=ct, cost=c)
logger.warning("LLM model not registered", provider=p, model_name=m)  # 매핑 실패

# Best-effort write 실패
logger.warning("Tracker best-effort write failed", exception=e, run_id=run_id)
```

---

## 11. 의존성 그래프

```
agent_run_router.py
    └── GetRunDetailUseCase
            └── AgentRunRepositoryInterface ── SqlAlchemyAgentRunRepository
                                                    └── MySQL

usage_router.py
    └── UsageAggregator
            └── LlmCallRepositoryInterface ── SqlAlchemyLlmCallRepository
                                                    └── MySQL

agent_builder_router.py
    └── RunAgentUseCase
            ├── AgentDefinitionRepositoryInterface
            ├── LlmModelRepositoryInterface
            ├── WorkflowCompiler                  ── LLMFactory (stream_usage=True, §14-3)
            ├── ConversationSummarizerInterface   ── reads ContextVar
            ├── ConversationMessageRepository
            └── RunTracker ★
                    ├── AgentRunRepositoryInterface
                    ├── LlmCallRepositoryInterface
                    ├── CostCalculator (TTL cache, §14-6)
                    │       ├── LlmModelRepositoryInterface
                    │       └── RunObservabilityConfig
                    └── ModelNameResolver
                            └── LlmModelRepositoryInterface

ContextVar[RunContext] (§14-2)
    ├── set by: RunAgentUseCase.execute() / _wrapped_tool_call
    └── read by: RAG adapters / Summarizer / 외부 툴 → tracker.record_retrieval()

WorkflowCompiler.compile()
    └── (LangGraph) ──[callbacks=[UsageCallback]]──► on_llm_end ──► RunTracker.record_llm_call
                                                                            └── (resolver + calculator + INSERT)

RunAgentUseCase.complete_run() (§14-5)
    └── UPDATE ai_run SET (prompt/completion/total_tokens, total_cost_usd, llm_call_count)
        = (SELECT SUM(...) FROM ai_llm_call WHERE run_id = ?)
```

---

## 12. 보안 / 권한

| 엔드포인트 | 권한 | 비고 |
|-----------|------|------|
| `GET /agents/runs/{run_id}` | 본인 OR admin | run.user_id == viewer.id 체크 |
| `GET /admin/usage/users` | admin only | `require_admin` dependency |
| `GET /admin/usage/llm-models` | admin only | |
| `GET /usage/me` | 본인 | user.id로 자동 필터 |
| `PATCH /llm-models/{id}/pricing` | admin only | M1에 포함 (V022 가격 컬럼 갱신) |

---

## 13. CLAUDE.md 규칙 체크

- [x] domain 레이어는 SQLAlchemy/LangChain 등 외부 의존성 없음 (`agent_run/`)
- [x] application 레이어가 흐름 제어 (Tracker / Aggregator / CostCalculator)
- [x] infrastructure에서만 ORM/LangChain callback 구현
- [x] interfaces 레이어는 Pydantic 스키마 변환만
- [x] Repository에서 commit/rollback 호출 금지 — Tracker 메서드 단위 세션 관리
- [x] 한 UseCase 내 동일 세션 사용 (RunAgentUseCase는 단일 session_factory 주입)
- [x] LOG-001 로깅 적용
- [x] TDD 순서 준수
- [x] config 하드코딩 금지 (요약본 컷오프 크기, 캐시 TTL 등은 config로)

---

## 14. Open Questions → 확정 (2026-05-18 결정 반영)

> 본 섹션은 Do 단계 진입 전에 결정해야 할 6개 항목의 **확정 결과**를 기록한다.
> 의사결정 이력 보존을 위해 항목은 삭제하지 않고 status를 갱신한다.

| # | 질문 | Status | 확정 내용 |
|---|------|:------:|----------|
| 1 | `ai_llm_call.purpose` 분류를 어디서 결정? | ✅ 확정 | **노드/툴 진입 시 명시적으로 결정**. Supervisor/Worker/Summarizer/RAG 툴/QueryRewrite/Rerank/HallucinationCheck 등 모든 진입 지점에서 `callback.set_purpose(RunPurpose.XXX)` 호출 의무화. purpose가 NULL이면 코드 누락으로 간주 → §4-3 lint 체크. |
| 2 | RAG 툴이 LangGraph 외부에서 호출되는 경우 컨텍스트 전달? | ✅ 확정 | **`ContextVar[RunContext]` 채택**. M1부터 도입(M4 지연 X). `application/agent_run/context.py` 신설. RunContext = (run_id, step_id, tool_call_id, callback). RAG 어댑터·Summarizer·외부 툴 모두 ContextVar에서 읽어 사용. |
| 3 | streaming 응답 토큰 집계 | ✅ 확정 | **LLMFactory에서 `stream_usage=True` 일괄 설정** (M1). `LLMFactory.create()` 내부에서 provider별로 적용 (OpenAI: `stream_usage=True`, Anthropic: 기본 포함, Ollama: 응답 자체에 포함). 어댑터 코드 변경 없이 일관 수집. |
| 4 | LangSmith trace_id가 callback 시점에 사용 가능? | ✅ 확정 | **`complete_run()` 시점에 회수**. callback 시점에는 nested run tree라 root trace_id가 불안정. `RunAgentUseCase.execute()` 마지막에 `TraceExtractor.extract()` 호출 후 `tracker.complete_run(trace_id=..., run_url=...)`로 전달. |
| 5 | `ai_run.total_tokens` 일관성 보장 방식 | ✅ 확정 | **`complete_run()`에서 `SUM(ai_llm_call.*)` 후 UPDATE**. 단일 run 단위라 동시성 문제 없음. SUM 실패 시 warning log + status는 SUCCESS 유지. SQL: `UPDATE ai_run SET (prompt/completion/total_tokens, total_cost_usd, llm_call_count) = (SELECT SUM(...) FROM ai_llm_call WHERE run_id = ?) WHERE id = ?`. |
| 6 | 가격 캐시 TTL | ✅ 확정 | **M1부터 TTL 캐시 도입** (5분 기본). `CostCalculator._cache`를 `(value, expires_at)` 튜플로 저장. TTL은 `RunObservabilityConfig.pricing_cache_ttl_seconds=300`로 설정. 후속 `llm-pricing-sync` Plan에서 push-based invalidation으로 확장. |
