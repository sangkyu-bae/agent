"""AgentRun 도메인 엔티티.

AGENT-OBS-001 §2-2:
- AgentRun: 사용자 질문 1회 = 1 row (ai_run)
- AgentRunStep: LangGraph 노드 실행 (ai_run_step)
- ToolCall: 툴 호출 (ai_tool_call)
- RetrievalSource: RAG 검색 근거 (ai_retrieval_source)
- LlmCall: LLM API 호출 1건 (ai_llm_call) — 사용자별·LLM별 집계의 기준 단위
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
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
    """Run 단위 엔티티. SUM(ai_llm_call.*)이 ai_run.* 합계로 영속화된다."""

    id: RunId
    conversation_id: str
    user_id: str
    agent_id: str
    llm_model_id: Optional[str]
    user_message_id: Optional[int]
    status: RunStatus
    langgraph_thread_id: str
    langsmith_trace_id: Optional[str]
    langsmith_run_url: Optional[str]
    token_usage: TokenUsage
    cost_usd: CostUsd
    llm_call_count: int
    started_at: datetime
    ended_at: Optional[datetime]
    latency_ms: Optional[int]
    error_message: Optional[str]
    error_stack: Optional[str]


@dataclass
class AgentRunStep:
    """LangGraph 노드 1회 실행."""

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
    """툴 호출 1회. 툴 내부 LLM 호출은 llm_model_id로 식별."""

    id: str
    run_id: RunId
    step_id: Optional[str]
    tool_name: str
    llm_model_id: Optional[str]
    arguments_json: Optional[dict[str, Any]]
    result_summary: Optional[str]
    result_json: Optional[dict[str, Any]]
    token_usage: Optional[TokenUsage]
    total_cost_usd: Optional[Decimal]
    latency_ms: Optional[int]
    status: str
    error_text: Optional[str]
    created_at: datetime


@dataclass
class RetrievalSource:
    """RAG 검색 1건의 근거 chunk."""

    id: str
    run_id: RunId
    tool_call_id: Optional[str]
    collection_name: str
    document_id: Optional[str]
    chunk_id: Optional[str]
    score: Optional[float]
    rank_index: Optional[int]
    content_preview: Optional[str]
    metadata_json: Optional[dict[str, Any]]
    created_at: datetime


@dataclass
class LlmCall:
    """LLM API 호출 1건 — 사용자별·LLM별 집계 기준 단위.

    user_id / agent_id / model_name / provider는 비정규화 (집계 성능 목적).
    매핑 실패 시 llm_model_id=None (경고 로그). model_name은 항상 스냅샷 저장.
    """

    id: str
    run_id: RunId
    step_id: Optional[str]
    tool_call_id: Optional[str]
    user_id: str
    agent_id: str
    llm_model_id: Optional[str]
    provider: str
    model_name: str
    purpose: Optional[RunPurpose]
    token_usage: TokenUsage
    input_price_per_1k_usd: Optional[Decimal]
    output_price_per_1k_usd: Optional[Decimal]
    cost_usd: CostUsd
    latency_ms: Optional[int]
    status: str
    error_text: Optional[str]
    created_at: datetime
