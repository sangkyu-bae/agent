"""AgentRun entities tests — mock 금지 (domain 규칙)."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.domain.agent_run.entities import (
    AgentRun,
    AgentRunStep,
    LlmCall,
    RetrievalSource,
    ToolCall,
)
from src.domain.agent_run.value_objects import (
    CostUsd,
    NodeType,
    RunId,
    RunPurpose,
    RunStatus,
    StepStatus,
    TokenUsage,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TestAgentRun:
    def test_construct_minimal_running_run(self) -> None:
        run = AgentRun(
            id=RunId("11111111-1111-1111-1111-111111111111"),
            conversation_id="conv-1",
            user_id="user-1",
            agent_id="agent-1",
            llm_model_id="m-1",
            user_message_id=None,
            status=RunStatus.RUNNING,
            langgraph_thread_id="conv-1",
            langsmith_trace_id=None,
            langsmith_run_url=None,
            token_usage=TokenUsage(),
            cost_usd=CostUsd(),
            llm_call_count=0,
            started_at=_now(),
            ended_at=None,
            latency_ms=None,
            error_message=None,
            error_stack=None,
        )
        assert run.status is RunStatus.RUNNING
        assert run.llm_call_count == 0

    def test_full_success_run(self) -> None:
        started = _now()
        ended = _now()
        run = AgentRun(
            id=RunId("22222222-2222-2222-2222-222222222222"),
            conversation_id="conv-2",
            user_id="user-2",
            agent_id="agent-2",
            llm_model_id="m-2",
            user_message_id=123,
            status=RunStatus.SUCCESS,
            langgraph_thread_id="conv-2",
            langsmith_trace_id="trace-xyz",
            langsmith_run_url="https://smith.langchain.com/abc",
            token_usage=TokenUsage(10, 20, 30),
            cost_usd=CostUsd(
                input_usd=Decimal("0.001"),
                output_usd=Decimal("0.002"),
                total_usd=Decimal("0.003"),
            ),
            llm_call_count=3,
            started_at=started,
            ended_at=ended,
            latency_ms=1500,
            error_message=None,
            error_stack=None,
        )
        assert run.status is RunStatus.SUCCESS
        assert run.token_usage.total_tokens == 30
        assert run.llm_call_count == 3
        assert run.langsmith_trace_id == "trace-xyz"


class TestAgentRunStep:
    def test_construct(self) -> None:
        step = AgentRunStep(
            id="step-1",
            run_id=RunId("11111111-1111-1111-1111-111111111111"),
            step_index=0,
            node_name="supervisor",
            node_type=NodeType.SUPERVISOR,
            llm_model_id="m-1",
            status=StepStatus.STARTED,
            input_summary="hello",
            output_summary=None,
            started_at=_now(),
            ended_at=None,
            latency_ms=None,
            error_text=None,
        )
        assert step.node_type is NodeType.SUPERVISOR
        assert step.status is StepStatus.STARTED


class TestToolCall:
    def test_construct(self) -> None:
        call = ToolCall(
            id="tool-1",
            run_id=RunId("11111111-1111-1111-1111-111111111111"),
            step_id="step-1",
            tool_name="rag_search",
            llm_model_id=None,
            arguments_json={"query": "hi"},
            result_summary="result preview",
            result_json=None,
            token_usage=TokenUsage(5, 5, 10),
            total_cost_usd=Decimal("0.0001"),
            latency_ms=200,
            status="SUCCESS",
            error_text=None,
            created_at=_now(),
        )
        assert call.tool_name == "rag_search"
        assert call.token_usage is not None
        assert call.token_usage.total_tokens == 10


class TestRetrievalSource:
    def test_construct(self) -> None:
        src = RetrievalSource(
            id="ret-1",
            run_id=RunId("11111111-1111-1111-1111-111111111111"),
            tool_call_id="tool-1",
            collection_name="policy_kb",
            document_id="doc-1",
            chunk_id="chunk-1",
            score=0.87,
            rank_index=0,
            content_preview="content preview",
            metadata_json={"source": "pdf"},
            created_at=_now(),
        )
        assert src.collection_name == "policy_kb"
        assert src.rank_index == 0


class TestLlmCall:
    def test_construct_success(self) -> None:
        call = LlmCall(
            id="llm-1",
            run_id=RunId("11111111-1111-1111-1111-111111111111"),
            step_id="step-1",
            tool_call_id=None,
            user_id="user-1",
            agent_id="agent-1",
            llm_model_id="m-1",
            provider="openai",
            model_name="gpt-4o",
            purpose=RunPurpose.SUPERVISOR,
            token_usage=TokenUsage(100, 50, 150),
            input_price_per_1k_usd=Decimal("0.005"),
            output_price_per_1k_usd=Decimal("0.015"),
            cost_usd=CostUsd(
                input_usd=Decimal("0.000500"),
                output_usd=Decimal("0.000750"),
                total_usd=Decimal("0.001250"),
            ),
            latency_ms=1200,
            status="SUCCESS",
            error_text=None,
            created_at=_now(),
        )
        assert call.provider == "openai"
        assert call.purpose is RunPurpose.SUPERVISOR
        assert call.token_usage.total_tokens == 150

    def test_construct_failed(self) -> None:
        call = LlmCall(
            id="llm-2",
            run_id=RunId("11111111-1111-1111-1111-111111111111"),
            step_id=None,
            tool_call_id=None,
            user_id="user-1",
            agent_id="agent-1",
            llm_model_id=None,
            provider="unknown",
            model_name="unknown-model",
            purpose=None,
            token_usage=TokenUsage(),
            input_price_per_1k_usd=None,
            output_price_per_1k_usd=None,
            cost_usd=CostUsd(),
            latency_ms=10,
            status="FAILED",
            error_text="rate limit exceeded",
            created_at=_now(),
        )
        assert call.status == "FAILED"
        assert call.llm_model_id is None
        assert call.error_text == "rate limit exceeded"
