"""AgentRun 도메인 Repository 인터페이스.

AGENT-OBS-001 §2-4:
- AgentRunRepositoryInterface: run / step / tool / retrieval 영속화
- LlmCallRepositoryInterface: LLM 호출 영속화 + 사용자별/LLM별 집계 쿼리

집계 결과 타입은 application 레이어의 schemas/aggregator에 의존하지 않도록
도메인 내부에 단순 dataclass(UserUsageRow, LlmUsageRow)로 정의한다.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from src.domain.agent_run.entities import (
    AgentRun,
    AgentRunStep,
    LlmCall,
    RetrievalSource,
    ToolCall,
)
from src.domain.agent_run.value_objects import RunId


@dataclass(frozen=True)
class UserUsageRow:
    """사용자별 기간 집계 결과."""

    user_id: str
    total_tokens: int
    total_cost_usd: Decimal
    call_count: int


@dataclass(frozen=True)
class LlmUsageRow:
    """LLM 모델별 기간 집계 결과."""

    llm_model_id: Optional[str]
    provider: str
    model_name: str
    total_tokens: int
    total_cost_usd: Decimal
    call_count: int


@dataclass(frozen=True)
class NodeUsageRow:
    """노드별 기간 집계 결과 (★ M4 / M3 step_id JOIN 효과).

    step_id가 NULL인 LLM 호출은 INNER JOIN으로 자연 제외된다
    (M2 이전 데이터 / graph 외 호출).
    """

    node_name: str
    call_count: int
    total_tokens: int
    total_cost_usd: Decimal


@dataclass(frozen=True)
class RunListFilters:
    """Admin Run list 필터 + 페이지네이션 (★ M5).

    모든 필터는 Optional — None이면 해당 조건 미적용.
    status는 RunStatus enum value (RUNNING/SUCCESS/FAILED/CANCELLED).
    """

    from_dt: Optional[datetime] = None
    to_dt: Optional[datetime] = None
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    status: Optional[str] = None
    limit: int = 20
    offset: int = 0


@dataclass(frozen=True)
class UsageSummaryRow:
    """대시보드 카드 4종 단일 응답 (Admin / Me 공용 — user_id 필터 옵션).

    `success_rate`는 응답 직전에 라우트/스키마 레이어에서 계산한다
    (도메인은 raw count만 책임).
    """

    from_dt: datetime
    to_dt: datetime
    total_runs: int
    success_runs: int
    failed_runs: int
    total_tokens: int
    total_cost_usd: Decimal


@dataclass(frozen=True)
class UsageTimeseriesPoint:
    """일자별 시계열 1포인트 (bucket = 'day' 고정 v1)."""

    bucket: date
    run_count: int
    total_tokens: int
    total_cost_usd: Decimal


class AgentRunRepositoryInterface(ABC):
    """ai_run / ai_run_step / ai_tool_call / ai_retrieval_source 영속화."""

    @abstractmethod
    async def save_run(self, run: AgentRun) -> AgentRun: ...

    @abstractmethod
    async def update_run(self, run: AgentRun) -> None: ...

    @abstractmethod
    async def find_run(self, run_id: RunId) -> Optional[AgentRun]: ...

    @abstractmethod
    async def apply_completion_totals(
        self,
        run_id: RunId,
        langsmith_trace_id: Optional[str],
        langsmith_run_url: Optional[str],
    ) -> None:
        """complete_run에서 호출: SUM(ai_llm_call.*) → ai_run.* UPDATE.

        Design §14-5: 단일 SQL로 SUBQUERY SUM UPDATE.
        status='SUCCESS', ended_at=NOW(), latency_ms=계산.
        """

    @abstractmethod
    async def mark_failed(
        self,
        run_id: RunId,
        error_message: Optional[str],
        error_stack: Optional[str],
    ) -> None:
        """fail_run에서 호출: status='FAILED' + 에러 정보 기록."""

    @abstractmethod
    async def save_step(self, step: AgentRunStep) -> AgentRunStep: ...

    @abstractmethod
    async def update_step(self, step: AgentRunStep) -> None: ...

    @abstractmethod
    async def save_tool_call(self, call: ToolCall) -> ToolCall: ...

    @abstractmethod
    async def update_tool_call(self, call: ToolCall) -> None: ...

    @abstractmethod
    async def save_retrieval(self, source: RetrievalSource) -> RetrievalSource: ...

    @abstractmethod
    async def find_steps(self, run_id: RunId) -> List[AgentRunStep]: ...

    @abstractmethod
    async def find_tool_calls(self, run_id: RunId) -> List[ToolCall]: ...

    @abstractmethod
    async def find_retrievals(self, run_id: RunId) -> List[RetrievalSource]: ...

    @abstractmethod
    async def attach_user_message(self, run_id: RunId, message_id: int) -> None:
        """retrieval-observability D2: ai_run.user_message_id deferred attach."""

    @abstractmethod
    async def find_runs_by_user_message(self, message_id: int) -> List[AgentRun]:
        """메시지 기준 run 조회 (조회 API)."""

    @abstractmethod
    async def list_runs(self, filters: "RunListFilters") -> List[AgentRun]:
        """M5: 필터 + ORDER BY started_at DESC + LIMIT/OFFSET."""

    @abstractmethod
    async def count_runs(self, filters: "RunListFilters") -> int:
        """M5: 같은 필터로 total row count — list_runs와 정합 보장."""


class LlmCallRepositoryInterface(ABC):
    """ai_llm_call 영속화 + 사용자별/LLM별/사용자×LLM 집계 쿼리."""

    @abstractmethod
    async def save(self, call: LlmCall) -> LlmCall: ...

    @abstractmethod
    async def find_by_run(self, run_id: RunId) -> List[LlmCall]: ...

    @abstractmethod
    async def aggregate_by_user(
        self, from_dt: datetime, to_dt: datetime
    ) -> List[UserUsageRow]: ...

    @abstractmethod
    async def aggregate_by_llm_model(
        self, from_dt: datetime, to_dt: datetime
    ) -> List[LlmUsageRow]: ...

    @abstractmethod
    async def aggregate_user_x_llm(
        self, user_id: str, from_dt: datetime, to_dt: datetime
    ) -> List[LlmUsageRow]: ...

    @abstractmethod
    async def aggregate_by_node(
        self, from_dt: datetime, to_dt: datetime
    ) -> List[NodeUsageRow]:
        """노드별 토큰/비용 집계 (M4 — JOIN ai_run_step + GROUP BY node_name)."""

    @abstractmethod
    async def aggregate_summary(
        self,
        from_dt: datetime,
        to_dt: datetime,
        user_id: Optional[str] = None,
    ) -> UsageSummaryRow:
        """M5: 카드 4종 단일 응답.

        - tokens/cost는 ai_llm_call 합계
        - run 수·성공/실패는 ai_run 합계
        - user_id 주어지면 두 sub-query 모두 동일 user_id 필터 적용
        """

    @abstractmethod
    async def aggregate_timeseries(
        self,
        from_dt: datetime,
        to_dt: datetime,
        user_id: Optional[str] = None,
    ) -> List[UsageTimeseriesPoint]:
        """M5: 일자별 GROUP BY DATE(started_at) — ai_run LEFT JOIN ai_llm_call.

        bucket=day 고정 (v1). 빈 일자는 응답에 포함하지 않는다 (FE에서 보간).
        """
