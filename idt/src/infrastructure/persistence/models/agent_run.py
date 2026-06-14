"""SQLAlchemy ORM models for AgentRun observability tables.

AGENT-OBS-001 §4-1. Maps to V021 migration (ai_run, ai_run_step, ai_tool_call,
ai_retrieval_source, ai_llm_call) and V022 (llm_model pricing columns).
"""
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.models.base import Base


class AgentRunModel(Base):
    """ai_run — 사용자 질문 1회 = 1 row."""

    __tablename__ = "ai_run"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False)
    llm_model_id: Mapped[str | None] = mapped_column(String(36))
    user_message_id: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    langgraph_thread_id: Mapped[str] = mapped_column(String(150), nullable=False)
    langsmith_trace_id: Mapped[str | None] = mapped_column(String(150))
    langsmith_run_url: Mapped[str | None] = mapped_column(String(500))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0"), nullable=False
    )
    llm_call_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    error_stack: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("idx_run_conversation", "conversation_id"),
        Index("idx_run_agent", "agent_id"),
        Index("idx_run_user_started", "user_id", "started_at"),
        Index("idx_run_llm_model", "llm_model_id"),
        Index("idx_run_status", "status"),
        Index("idx_run_started_at", "started_at"),
    )


class AgentRunStepModel(Base):
    """ai_run_step — LangGraph 노드 실행."""

    __tablename__ = "ai_run_step"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    node_name: Mapped[str] = mapped_column(String(100), nullable=False)
    node_type: Mapped[str] = mapped_column(String(30), nullable=False)
    llm_model_id: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    input_summary: Mapped[str | None] = mapped_column(Text)
    output_summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_text: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("idx_step_run", "run_id", "step_index"),)


class ToolCallModel(Base):
    """ai_tool_call — 툴 호출."""

    __tablename__ = "ai_tool_call"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    step_id: Mapped[str | None] = mapped_column(String(36))
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    llm_model_id: Mapped[str | None] = mapped_column(String(36))
    arguments_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    result_summary: Mapped[str | None] = mapped_column(Text)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    total_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("idx_tool_run", "run_id"),
        Index("idx_tool_name", "tool_name"),
        Index("idx_tool_llm_model", "llm_model_id"),
    )


class LlmCallModel(Base):
    """ai_llm_call — LLM API 호출 1건 (사용자별·LLM별 집계의 기준).

    user_id / agent_id / model_name / provider는 비정규화 (집계 성능).
    """

    __tablename__ = "ai_llm_call"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    step_id: Mapped[str | None] = mapped_column(String(36))
    tool_call_id: Mapped[str | None] = mapped_column(String(36))
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False)
    llm_model_id: Mapped[str | None] = mapped_column(String(36))
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(150), nullable=False)
    purpose: Mapped[str | None] = mapped_column(String(50))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_price_per_1k_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    output_price_per_1k_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    input_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0"), nullable=False
    )
    output_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0"), nullable=False
    )
    total_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0"), nullable=False
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("idx_llm_call_user_created", "user_id", "created_at"),
        Index("idx_llm_call_model_created", "llm_model_id", "created_at"),
        Index("idx_llm_call_user_model", "user_id", "llm_model_id"),
        Index("idx_llm_call_agent", "agent_id"),
        Index("idx_llm_call_run", "run_id"),
    )


class RetrievalSourceModel(Base):
    """ai_retrieval_source — RAG 검색 근거 chunk."""

    __tablename__ = "ai_retrieval_source"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tool_call_id: Mapped[str | None] = mapped_column(String(36))
    collection_name: Mapped[str] = mapped_column(String(100), nullable=False)
    document_id: Mapped[str | None] = mapped_column(String(150))
    chunk_id: Mapped[str | None] = mapped_column(String(150))
    score: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    rank_index: Mapped[int | None] = mapped_column(Integer)
    content_preview: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("idx_retrieval_run", "run_id"),
        Index("idx_retrieval_collection", "collection_name"),
    )
