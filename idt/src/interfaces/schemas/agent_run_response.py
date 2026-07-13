"""Agent Run observability API response schemas (M4 + M5 dashboard).

agent-run-observability-m4 Design §6.3 / agent-run-admin-dashboard Design §4.3.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


# ── Common DTOs ────────────────────────────────────────────────────


class TokenUsageDto(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class CostUsdDto(BaseModel):
    input_usd: Decimal = Decimal("0")
    output_usd: Decimal = Decimal("0")
    total_usd: Decimal = Decimal("0")


class RetrievalDto(BaseModel):
    id: str
    collection_name: str
    document_id: Optional[str] = None
    chunk_id: Optional[str] = None
    score: Optional[float] = None
    rank_index: Optional[int] = None
    content_preview: Optional[str] = None
    created_at: datetime
    # retrieval-observability (V046): 검색 실행 컨텍스트
    search_query: Optional[str] = None
    query_source: Optional[str] = None
    search_mode: Optional[str] = None
    bm25_score: Optional[float] = None
    vector_score: Optional[float] = None
    bm25_rank: Optional[int] = None
    vector_rank: Optional[int] = None
    fusion_source: Optional[str] = None


class LlmCallDto(BaseModel):
    id: str
    purpose: Optional[str] = None
    provider: str
    model_name: str
    llm_model_id: Optional[str] = None
    token_usage: TokenUsageDto
    cost_usd: CostUsdDto
    latency_ms: Optional[int] = None
    status: str
    created_at: datetime


class ToolCallDto(BaseModel):
    id: str
    tool_name: str
    arguments: Optional[dict] = None
    result_summary: Optional[str] = None
    latency_ms: Optional[int] = None
    status: str
    retrievals: List[RetrievalDto] = []
    llm_calls: List[LlmCallDto] = []


class StepDto(BaseModel):
    id: str
    step_index: int
    node_name: str
    node_type: str
    status: str
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    latency_ms: Optional[int] = None
    error_text: Optional[str] = None
    llm_calls: List[LlmCallDto] = []
    tool_calls: List[ToolCallDto] = []


class RunDto(BaseModel):
    id: str
    status: str
    user_id: str
    agent_id: str
    conversation_id: str
    llm_model_id: Optional[str] = None
    langgraph_thread_id: str
    langsmith_trace_id: Optional[str] = None
    langsmith_run_url: Optional[str] = None
    token_usage: TokenUsageDto
    cost_usd: CostUsdDto
    llm_call_count: int
    started_at: datetime
    ended_at: Optional[datetime] = None
    latency_ms: Optional[int] = None
    error_message: Optional[str] = None


class RunDetailResponse(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    run: RunDto
    steps: List[StepDto] = []
    orphan_llm_calls: List[LlmCallDto] = []

    @classmethod
    def from_dto(cls, dto) -> "RunDetailResponse":
        return cls(
            run=_run_to_dto(dto.run),
            steps=[_step_node_to_dto(s) for s in dto.steps],
            orphan_llm_calls=[_llm_to_dto(lc) for lc in dto.orphan_llm_calls],
        )


# ── Message Retrievals (retrieval-observability §4.6) ─────────────


class QueryRetrievalGroupDto(BaseModel):
    """재작성 쿼리 1개 단위의 근거 그룹."""

    search_query: Optional[str] = None
    query_source: Optional[str] = None
    search_mode: Optional[str] = None
    sources: List[RetrievalDto] = []


class MessageRunRetrievalsDto(BaseModel):
    """run 1개의 검색 근거 (보통 메시지당 1 run, 재시도 시 복수)."""

    run_id: str
    agent_id: str
    langsmith_run_url: Optional[str] = None
    groups: List[QueryRetrievalGroupDto] = []


class MessageRetrievalsResponse(BaseModel):
    message_id: int
    runs: List[MessageRunRetrievalsDto] = []

    @classmethod
    def from_dto(cls, dto) -> "MessageRetrievalsResponse":
        return cls(
            message_id=dto.message_id,
            runs=[
                MessageRunRetrievalsDto(
                    run_id=node.run.id.value,
                    agent_id=node.run.agent_id,
                    langsmith_run_url=node.run.langsmith_run_url,
                    groups=[
                        QueryRetrievalGroupDto(
                            search_query=g.search_query,
                            query_source=g.query_source,
                            search_mode=g.search_mode,
                            sources=[_retrieval_to_dto(r) for r in g.sources],
                        )
                        for g in node.groups
                    ],
                )
                for node in dto.runs
            ],
        )


# ── Usage Responses ───────────────────────────────────────────────


class UsageByUserRow(BaseModel):
    user_id: str
    total_tokens: int
    total_cost_usd: Decimal
    call_count: int


class UsageByUserResponse(BaseModel):
    from_dt: datetime
    to_dt: datetime
    rows: List[UsageByUserRow]

    @classmethod
    def from_rows(cls, rows, from_dt: datetime, to_dt: datetime) -> "UsageByUserResponse":
        return cls(
            from_dt=from_dt,
            to_dt=to_dt,
            rows=[
                UsageByUserRow(
                    user_id=r.user_id,
                    total_tokens=r.total_tokens,
                    total_cost_usd=r.total_cost_usd,
                    call_count=r.call_count,
                )
                for r in rows
            ],
        )


class UsageByLlmRow(BaseModel):
    llm_model_id: Optional[str] = None
    provider: str
    model_name: str
    total_tokens: int
    total_cost_usd: Decimal
    call_count: int


class UsageByLlmResponse(BaseModel):
    from_dt: datetime
    to_dt: datetime
    rows: List[UsageByLlmRow]

    @classmethod
    def from_rows(cls, rows, from_dt: datetime, to_dt: datetime) -> "UsageByLlmResponse":
        return cls(
            from_dt=from_dt,
            to_dt=to_dt,
            rows=[
                UsageByLlmRow(
                    llm_model_id=r.llm_model_id,
                    provider=r.provider,
                    model_name=r.model_name,
                    total_tokens=r.total_tokens,
                    total_cost_usd=r.total_cost_usd,
                    call_count=r.call_count,
                )
                for r in rows
            ],
        )


class UsageByNodeRow(BaseModel):
    node_name: str
    call_count: int
    total_tokens: int
    total_cost_usd: Decimal


class UsageByNodeResponse(BaseModel):
    from_dt: datetime
    to_dt: datetime
    rows: List[UsageByNodeRow]

    @classmethod
    def from_rows(cls, rows, from_dt: datetime, to_dt: datetime) -> "UsageByNodeResponse":
        return cls(
            from_dt=from_dt,
            to_dt=to_dt,
            rows=[
                UsageByNodeRow(
                    node_name=r.node_name,
                    call_count=r.call_count,
                    total_tokens=r.total_tokens,
                    total_cost_usd=r.total_cost_usd,
                )
                for r in rows
            ],
        )


# ── M5: Admin Run List Responses ──────────────────────────────────


class RunRowDto(BaseModel):
    """Run list 한 row (light — steps/tool_calls join 없음, ai_run만)."""

    id: str
    user_id: str
    agent_id: str
    conversation_id: str
    status: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    latency_ms: Optional[int] = None
    total_tokens: int = 0
    total_cost_usd: Decimal = Decimal("0")
    llm_call_count: int = 0
    error_message: Optional[str] = None


class RunListResponse(BaseModel):
    from_dt: Optional[datetime] = None
    to_dt: Optional[datetime] = None
    limit: int
    offset: int
    total: int
    rows: List[RunRowDto]

    @classmethod
    def from_dto(cls, dto) -> "RunListResponse":
        return cls(
            from_dt=dto.from_dt,
            to_dt=dto.to_dt,
            limit=dto.limit,
            offset=dto.offset,
            total=dto.total,
            rows=[
                RunRowDto(
                    id=r.id.value,
                    user_id=r.user_id,
                    agent_id=r.agent_id,
                    conversation_id=r.conversation_id,
                    status=(
                        r.status.value
                        if hasattr(r.status, "value")
                        else str(r.status)
                    ),
                    started_at=r.started_at,
                    ended_at=r.ended_at,
                    latency_ms=r.latency_ms,
                    total_tokens=r.token_usage.total_tokens,
                    total_cost_usd=r.cost_usd.total_usd,
                    llm_call_count=r.llm_call_count,
                    error_message=r.error_message,
                )
                for r in dto.rows
            ],
        )


# ── M5: Dashboard Summary & Timeseries Responses ──────────────────


class UsageSummaryResponse(BaseModel):
    """대시보드 카드 4종 단일 응답 — admin/me 공용 (route 가 user_id 주입)."""

    from_dt: datetime
    to_dt: datetime
    total_runs: int
    success_runs: int
    failed_runs: int
    success_rate: float  # 0..1 — 서버 계산 (FE 0으로 나눔 방지)
    total_tokens: int
    total_cost_usd: Decimal

    @classmethod
    def from_row(cls, row) -> "UsageSummaryResponse":
        total = row.total_runs
        rate = (row.success_runs / total) if total > 0 else 0.0
        return cls(
            from_dt=row.from_dt,
            to_dt=row.to_dt,
            total_runs=row.total_runs,
            success_runs=row.success_runs,
            failed_runs=row.failed_runs,
            success_rate=round(rate, 4),
            total_tokens=row.total_tokens,
            total_cost_usd=row.total_cost_usd,
        )


class UsageTimeseriesPointDto(BaseModel):
    bucket: date
    run_count: int
    total_tokens: int
    total_cost_usd: Decimal


class UsageTimeseriesResponse(BaseModel):
    from_dt: datetime
    to_dt: datetime
    bucket: str = "day"
    points: List[UsageTimeseriesPointDto]

    @classmethod
    def from_points(
        cls, points, from_dt: datetime, to_dt: datetime
    ) -> "UsageTimeseriesResponse":
        return cls(
            from_dt=from_dt,
            to_dt=to_dt,
            bucket="day",
            points=[
                UsageTimeseriesPointDto(
                    bucket=p.bucket,
                    run_count=p.run_count,
                    total_tokens=p.total_tokens,
                    total_cost_usd=p.total_cost_usd,
                )
                for p in points
            ],
        )


# ── Domain → Pydantic converters ──────────────────────────────────


def _token_usage_to_dto(tu) -> TokenUsageDto:
    return TokenUsageDto(
        prompt_tokens=tu.prompt_tokens,
        completion_tokens=tu.completion_tokens,
        total_tokens=tu.total_tokens,
    )


def _cost_to_dto(cu) -> CostUsdDto:
    return CostUsdDto(
        input_usd=cu.input_usd,
        output_usd=cu.output_usd,
        total_usd=cu.total_usd,
    )


def _run_to_dto(run) -> RunDto:
    return RunDto(
        id=run.id.value,
        status=run.status.value if hasattr(run.status, "value") else str(run.status),
        user_id=run.user_id,
        agent_id=run.agent_id,
        conversation_id=run.conversation_id,
        llm_model_id=run.llm_model_id,
        langgraph_thread_id=run.langgraph_thread_id,
        langsmith_trace_id=run.langsmith_trace_id,
        langsmith_run_url=run.langsmith_run_url,
        token_usage=_token_usage_to_dto(run.token_usage),
        cost_usd=_cost_to_dto(run.cost_usd),
        llm_call_count=run.llm_call_count,
        started_at=run.started_at,
        ended_at=run.ended_at,
        latency_ms=run.latency_ms,
        error_message=run.error_message,
    )


def _llm_to_dto(lc) -> LlmCallDto:
    return LlmCallDto(
        id=lc.id,
        purpose=lc.purpose.value if lc.purpose else None,
        provider=lc.provider,
        model_name=lc.model_name,
        llm_model_id=lc.llm_model_id,
        token_usage=_token_usage_to_dto(lc.token_usage),
        cost_usd=_cost_to_dto(lc.cost_usd),
        latency_ms=lc.latency_ms,
        status=lc.status,
        created_at=lc.created_at,
    )


def _retrieval_to_dto(r) -> RetrievalDto:
    return RetrievalDto(
        id=r.id,
        collection_name=r.collection_name,
        document_id=r.document_id,
        chunk_id=r.chunk_id,
        score=r.score,
        rank_index=r.rank_index,
        content_preview=r.content_preview,
        created_at=r.created_at,
        search_query=r.search_query,
        query_source=r.query_source,
        search_mode=r.search_mode,
        bm25_score=r.bm25_score,
        vector_score=r.vector_score,
        bm25_rank=r.bm25_rank,
        vector_rank=r.vector_rank,
        fusion_source=r.fusion_source,
    )


def _tool_call_node_to_dto(node) -> ToolCallDto:
    tc = node.tool_call
    return ToolCallDto(
        id=tc.id,
        tool_name=tc.tool_name,
        arguments=tc.arguments_json,
        result_summary=tc.result_summary,
        latency_ms=tc.latency_ms,
        status=tc.status,
        retrievals=[_retrieval_to_dto(r) for r in node.retrievals],
        llm_calls=[_llm_to_dto(lc) for lc in node.llm_calls],
    )


def _step_node_to_dto(node) -> StepDto:
    s = node.step
    return StepDto(
        id=s.id,
        step_index=s.step_index,
        node_name=s.node_name,
        node_type=s.node_type.value if hasattr(s.node_type, "value") else str(s.node_type),
        status=s.status.value if hasattr(s.status, "value") else str(s.status),
        input_summary=s.input_summary,
        output_summary=s.output_summary,
        started_at=s.started_at,
        ended_at=s.ended_at,
        latency_ms=s.latency_ms,
        error_text=s.error_text,
        llm_calls=[_llm_to_dto(lc) for lc in node.llm_calls],
        tool_calls=[_tool_call_node_to_dto(tc) for tc in node.tool_calls],
    )
