"""포트가 주고받는 값 타입.

Design Ref: stock-analysis-agents §4, v0.2
§14.2 — 포트는 application 의 Protocol 이고 어댑터는
구조적 타이핑으로 맞춘다. 어댑터(infrastructure)가
application 을 import 하지 않도록 값 타입은 domain 에 둔다.
포트는 예외를 던지지 않고 실패를 값으로 돌려준다 —
한 종목·한 섹션 실패가 회차를 멈추지 않게 (§10).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any


class ToolSource(StrEnum):
    KIS = "kis"
    DART = "dart"
    PERPLEXITY = "perplexity"
    TAVILY = "tavily"


@dataclass(frozen=True)
class AgentRunOutcome:
    answer: str
    run_id: str | None
    tokens: int = 0
    cost_usd: Decimal = Decimal("0")
    failed: bool = False
    error: str | None = None
    """실패 코드 또는 짧은 사유 (예: RUN_AS_USER_INVALID,
    QUERY_TOO_LONG, RUN_FAILED: ...)."""


@dataclass(frozen=True)
class ToolOutcome:
    source: ToolSource
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    payload: Any = None
    """JSON 으로 읽힌 결과. 못 읽으면 None 이고 원문은 text 에 있다."""
    text: str = ""
    is_error: bool = False
    error_code: str | None = None
    cost_usd: Decimal = Decimal("0")
    """외부 과금 도구(Perplexity)가 응답에 실은 추정 비용."""
