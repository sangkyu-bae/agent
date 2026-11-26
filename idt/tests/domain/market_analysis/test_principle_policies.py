"""원칙 선택 · 합치기 키 (design §6 PrincipleSelectionPolicy, Q7)."""

from __future__ import annotations

from datetime import datetime

from src.domain.market_analysis.principle import (
    PrincipleMergePolicy,
    PrincipleRecord,
    PrincipleSelectionPolicy,
    principle_key,
)


def _p(
    pid, scope="buy", priority="medium", confidence=5, support=1, active=True, day=1
):
    return PrincipleRecord(
        id=pid,
        condition_text=f"조건{pid}",
        action_text=f"행동{pid}",
        scope=scope,
        priority=priority,
        confidence=confidence,
        supporting_count=support,
        is_active=active,
        created_at=datetime(2026, 11, day),
    )


def test_selects_active_matching_scope_in_priority_order():
    principles = [
        _p(1, priority="low", confidence=10),
        _p(2, priority="high", confidence=3),
        _p(3, priority="medium", confidence=9, support=1),
        _p(4, priority="medium", confidence=9, support=4),
        _p(5, scope="sell", priority="high"),
        _p(6, scope="all", priority="medium", confidence=1),
        _p(7, priority="high", active=False),
    ]
    picked = PrincipleSelectionPolicy.select(principles, scope="buy", limit=10)
    assert [p.id for p in picked] == [2, 4, 3, 6, 1]
    assert [
        p.id
        for p in PrincipleSelectionPolicy.select(principles, scope="sell", limit=10)
    ] == [5, 6]


def test_limit_and_zero_limit():
    principles = [_p(i, day=i) for i in range(1, 13)]
    picked = PrincipleSelectionPolicy.select(principles, scope="buy", limit=10)
    assert [p.id for p in picked] == list(range(1, 11))  # 동점이면 오래된 순
    assert PrincipleSelectionPolicy.select(principles, scope="buy", limit=0) == []


def test_text_shows_condition_action_and_support():
    assert (
        _p(1, confidence=7, support=3).text == "조건1 → 행동1 (확신도 7, 근거 거래 3건)"
    )


def test_merge_key_ignores_spacing_and_case_but_not_scope():
    a = principle_key("갭 상승  다음 날", "진입하지 않는다 ", "buy")
    b = principle_key(" 갭 상승 다음 날", "진입하지  않는다", "buy")
    assert a == b
    assert principle_key("RSI 70 이상", "x", "buy") == principle_key(
        "rsi 70 이상", "x", "buy"
    )
    assert a != principle_key("갭 상승 다음 날", "진입하지 않는다", "sell")
    assert PrincipleMergePolicy.merged_confidence(4, 7) == 7
    assert PrincipleMergePolicy.merged_confidence(8, 2) == 8
