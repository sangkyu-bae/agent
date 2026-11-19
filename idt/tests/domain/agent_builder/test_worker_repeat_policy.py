"""worker_repeat_policy — 같은 워커 연속 호출 판정 (claude-agent-e2e-fixes Design §4.2, D6·D7)."""
import pytest
from src.domain.agent_builder.worker_repeat_policy import (
    next_repeat_state,
    repeat_exhausted,
)


@pytest.mark.parametrize("prev,count,routed,expected", [
    ("a", 1, "a", ("a", 2)),
    ("a", 2, "b", ("b", 1)),
    ("", 0, "a", ("a", 1)),
    ("a", 2, "__end__", ("", 0)),
    ("a", 2, "", ("", 0)),
])
def test_next_repeat_state(prev, count, routed, expected):  # D6
    assert next_repeat_state(prev, count, routed) == expected


@pytest.mark.parametrize("worker,repeat_worker,count,limit,expected", [
    ("a", "a", 2, 2, True),
    ("a", "a", 3, 2, True),
    ("a", "a", 1, 2, False),
    ("b", "a", 5, 2, False),
    ("a", "a", 9, 0, False),   # limit 0 = 비활성
    ("", "", 0, 2, False),
])
def test_repeat_exhausted(worker, repeat_worker, count, limit, expected):  # D7
    assert repeat_exhausted(worker, repeat_worker, count, limit) is expected
