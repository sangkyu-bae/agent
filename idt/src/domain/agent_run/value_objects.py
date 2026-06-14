"""AgentRun 도메인 값 객체.

AGENT-OBS-001 §2-1: RunId, RunStatus, StepStatus, NodeType, RunPurpose,
TokenUsage, CostUsd.

agent-run-streaming-sse Design §3.1 / §3.2:
AgentRunEventType, AgentRunEvent — transport-독립 SSE/WS 이벤트 VO.

외부 의존성 금지 — dataclass + Enum + Decimal + 표준 datetime/typing만 사용한다.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional


@dataclass(frozen=True)
class RunId:
    """ai_run.id (UUID4 36자)."""

    value: str

    def __post_init__(self) -> None:
        if not self.value or len(self.value) != 36:
            raise ValueError("RunId must be a UUID string (36 chars)")


class RunStatus(str, Enum):
    """ai_run.status."""

    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepStatus(str, Enum):
    """ai_run_step.status."""

    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class NodeType(str, Enum):
    """ai_run_step.node_type."""

    SUPERVISOR = "SUPERVISOR"
    WORKER = "WORKER"
    GATE = "GATE"
    OTHER = "OTHER"


class RunPurpose(str, Enum):
    """ai_llm_call.purpose — LLM 호출 목적.

    노드/툴 진입 시 명시적으로 set_purpose() 호출 의무 (Design §14-1).
    """

    SUPERVISOR = "supervisor"
    WORKER = "worker"
    SUMMARIZER = "summarizer"
    QUERY_REWRITE = "query_rewrite"
    RERANK = "rerank"
    HALLUCINATION_CHECK = "hallucination_check"
    OTHER = "other"


@dataclass(frozen=True)
class TokenUsage:
    """LLM 호출 1건의 토큰 사용량."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __post_init__(self) -> None:
        if (
            self.prompt_tokens < 0
            or self.completion_tokens < 0
            or self.total_tokens < 0
        ):
            raise ValueError("Token counts must be non-negative")

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


@dataclass(frozen=True)
class CostUsd:
    """USD 비용. 정밀도 6자리 (DECIMAL(12,6)).

    호출 시점 가격 × 토큰으로 계산되어 ai_llm_call에 스냅샷 저장된다.
    """

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


# ── agent-run-streaming-sse Design §3 ────────────────────────────────────


class AgentRunEventType(str, Enum):
    """transport-독립 agent 실행 이벤트 타입.

    Plan §3.1 FR-05의 9개 카탈로그. SSE event 라인과 WS message type에 그대로 매핑.
    """

    RUN_STARTED = "run_started"
    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"
    STEP_REASONING = "step_reasoning"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    TOKEN = "token"
    ANSWER_COMPLETED = "answer_completed"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


@dataclass(frozen=True)
class AgentRunEvent:
    """transport-독립 agent 실행 이벤트 (Design §3.2).

    payload는 event_type별로 Design §3.3에 정의된 키만 포함한다.
    run_id는 RUN_STARTED 이벤트 발행 시점에 결정되므로 그 이전(또는 관측성
    비활성 모드)에는 None이 될 수 있다.
    """

    seq: int
    event_type: AgentRunEventType
    run_id: Optional[str]
    payload: Mapping[str, Any]
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.seq < 0:
            raise ValueError("seq must be non-negative")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC)")
