"""매매 원칙 · 저널 값 타입과 결정론 정책 (module-7).

Design Ref: stock-analysis-agents §6 PrincipleSelectionPolicy, DD9, Plan FR-12 · Q7.
- 선택: 활성 원칙 중 판단 종류(scope)가 맞거나 all 인 것 → priority(high>medium>low)
  → confidence → supporting_count → 오래된 순, 상위 N
- 합치기: 조건·행동·scope 가 공백·대소문자만 다르면 같은 원칙으로 본다.
  새 행을 만들지 않고 근거 거래 수를 1 올리고 확신도는 큰 쪽을 둔다
- 후보는 기본 비활성(DD9) — 판단 규칙이 근거 없이 바뀌지 않게 운영자가 켠다
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

Scope = Literal["buy", "sell", "all"]
Priority = Literal["high", "medium", "low"]
PRIORITY_RANK: dict[str, int] = {"high": 0, "medium": 1, "low": 2}
MAX_CANDIDATES_PER_JOURNAL = 5
_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class PrincipleRecord:
    id: int
    condition_text: str
    action_text: str
    scope: str
    priority: str
    confidence: int
    supporting_count: int
    is_active: bool
    created_at: datetime

    @property
    def text(self) -> str:
        return (
            f"{self.condition_text} → {self.action_text} "
            f"(확신도 {self.confidence}, 근거 거래 {self.supporting_count}건)"
        )


@dataclass(frozen=True)
class PrincipleCandidate:
    condition: str
    action: str
    reason: str | None
    scope: Scope
    priority: Priority
    confidence: int


def principle_key(condition: str, action: str, scope: str) -> tuple[str, str, str]:
    def norm(text: str) -> str:
        return _SPACE.sub(" ", text).strip().lower()

    return norm(condition), norm(action), scope


class PrincipleSelectionPolicy:
    @staticmethod
    def select(
        principles: list[PrincipleRecord], *, scope: str, limit: int
    ) -> list[PrincipleRecord]:
        if limit <= 0:
            return []
        eligible = [p for p in principles if p.is_active and p.scope in (scope, "all")]
        eligible.sort(
            key=lambda p: (
                PRIORITY_RANK.get(p.priority, 9),
                -p.confidence,
                -p.supporting_count,
                p.created_at,
                p.id,
            )
        )
        return eligible[:limit]


class PrincipleMergePolicy:
    @staticmethod
    def merged_confidence(existing: int, incoming: int) -> int:
        return max(existing, incoming)


# ── 저널 재료 (포트가 돌려주는 값) ──────────────────────────────────────────


@dataclass(frozen=True)
class DecisionSummary:
    kind: str
    decision: str
    score: int | None
    confidence: int | None
    price_at_decision: Decimal | None
    target_price: Decimal | None
    stop_loss: Decimal | None
    rationale: str | None
    skip_reason: str | None
    created_at: datetime


@dataclass(frozen=True)
class ClosedPosition:
    id: int
    symbol: str
    name: str | None
    sector: str | None
    entry_price: Decimal
    entry_at: datetime
    exit_price: Decimal
    exit_at: datetime
    exit_reason: str
    profit_rate: Decimal
    holding_days: int
    target_price: Decimal
    stop_loss: Decimal


@dataclass(frozen=True)
class JournalDraft:
    position_id: int
    one_line: str | None
    situation: str | None
    evaluation: str | None
    lessons: tuple[str, ...]
    tags: tuple[str, ...]
    raw_answer: str | None
    run_id: str | None
    created_at: datetime
