"""청산 저널 · 원칙 후보 (design §2.2 ⑦, §7 journal, DD8 · DD9, U12)."""

from __future__ import annotations

import dataclasses
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

from src.application.market_analysis.journal import JournalWriter
from src.domain.market_analysis.principle import ClosedPosition, DecisionSummary
from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.domain.market_analysis.value_objects import AgentRole

from .fakes import (
    FakeExtractor,
    FakeJournals,
    FakePrincipleStore,
    FakeRoles,
    FakeRunner,
    FakeSettings,
    FakeTools,
)

NOW = datetime(2026, 11, 26, 6, 40)
SETTING = dataclasses.replace(
    MarketAnalysisSetting.defaults(), kis_server_id="kis-1", run_as_user_id="7"
)
POSITION = ClosedPosition(
    id=9,
    symbol="000660",
    name="SK하이닉스",
    sector="반도체",
    entry_price=Decimal("10000"),
    entry_at=datetime(2026, 11, 20, 1, 0),
    exit_price=Decimal("9400"),
    exit_at=NOW,
    exit_reason="stop",
    profit_rate=Decimal("-6.0000"),
    holding_days=6,
    target_price=Decimal("12000"),
    stop_loss=Decimal("9500"),
)
DECISIONS = [
    DecisionSummary(
        "buy",
        "enter",
        8,
        None,
        Decimal("10000"),
        Decimal("12000"),
        Decimal("9500"),
        "수급 개선",
        None,
        datetime(2026, 11, 20, 1),
    ),
    DecisionSummary(
        "sell",
        "sell",
        None,
        None,
        Decimal("9400"),
        None,
        None,
        "손절가 도달 (결정론 청산)",
        None,
        NOW,
    ),
]
ANSWER = (
    '```json\n{"one_line": "갭 상승 추격 진입 후 손절", "situation": "s", '
    '"evaluation": "e", "lessons": ["갭 추격 금지"], "tags": ["gap"], '
    '"principle_candidates": [{"condition": "갭 상승 다음 날", '
    '"action": "진입하지 않는다", "reason": "이번 손절", "scope": "BUY", '
    '"priority": "high", "confidence": 3}]}\n```'
)


def _writer(
    answer=ANSWER,
    setting=SETTING,
    journals=None,
    roles=None,
    extractor=None,
    fail=False,
):
    tools = FakeTools()
    runner = FakeRunner(
        answers={"journal": answer}, fail_agents={"journal"} if fail else None
    )
    journals = journals or FakeJournals(POSITION, DECISIONS)
    principles = FakePrincipleStore()
    writer = JournalWriter(
        tools=tools,
        runner=runner,
        roles=roles or FakeRoles(),
        journals=journals,
        principles=principles,
        settings=FakeSettings(setting),
        extractor=extractor,
        logger=MagicMock(),
        now_utc=lambda: NOW,
    )
    return writer, runner, journals, principles, tools


async def test_writes_journal_and_inactive_candidates_u12():
    writer, runner, journals, principles, tools = _writer()
    assert await writer(9, "r") == 1
    (j,) = journals.saved
    assert (j.position_id, j.one_line, j.lessons, j.tags) == (
        9,
        "갭 상승 추격 진입 후 손절",
        ("갭 추격 금지",),
        ("gap",),
    )
    assert j.raw_answer is None and j.run_id == "run-journal"
    (batch,) = principles.added
    assert batch["journal_id"] == 1 and batch["auto_activate"] is False  # DD9 기본
    (c,) = batch["candidates"]
    assert (c.condition, c.action, c.scope, c.priority, c.confidence) == (
        "갭 상승 다음 날",
        "진입하지 않는다",
        "buy",
        "high",
        3,
    )
    ctx = runner.runs[0]["reference_context"]
    assert (
        "[거래 결과]" in ctx and "실현 수익률 -6.0000%" in ctx and "손절가 도달" in ctx
    )
    assert "buy:enter 점수 8" in ctx and "근거: 수급 개선" in ctx
    (call,) = [c for c in tools.calls if c[1] == "get_price_history"]
    assert call[2]["start"] == "2026-11-20" and call[2]["end"] == "2026-11-26"


async def test_auto_activate_setting_is_passed():
    setting = dataclasses.replace(SETTING, principle_auto_activate=True)
    writer, _, _, principles, _ = _writer(setting=setting)
    await writer(9, "r")
    assert principles.added[0]["auto_activate"] is True


async def test_parse_failure_saves_raw_answer_only_dd8():
    ex = FakeExtractor(None)
    writer, _, journals, principles, _ = _writer(
        answer="복기: 갭 추격이 문제였다", extractor=ex
    )
    assert await writer(9, "r") == 1
    (j,) = journals.saved
    assert j.raw_answer == "복기: 갭 추격이 문제였다" and j.one_line is None
    assert principles.added == [] and ex.calls == 1


async def test_existing_journal_skips_agent():
    journals = FakeJournals(POSITION, DECISIONS)
    journals.existing.add(9)
    writer, runner, _, _, _ = _writer(journals=journals)
    assert await writer(9, "r") is None and runner.runs == []


async def test_not_closed_unmapped_or_failed_agent_writes_nothing():
    writer, runner, journals, _, _ = _writer(journals=FakeJournals(None))
    assert await writer(9, "r") is None and runner.runs == []

    roles = FakeRoles({r: r.value for r in AgentRole if r is not AgentRole.JOURNAL})
    writer, runner, journals, _, _ = _writer(roles=roles)
    assert await writer(9, "r") is None and runner.runs == [] and journals.saved == []

    writer, _, journals, _, _ = _writer(fail=True)
    assert await writer(9, "r") is None and journals.saved == []


async def test_candidates_are_capped_at_five_with_defaults():
    many = ",".join(
        f'{{"condition": "c{i}", "action": "a{i}", "confidence": 2}}' for i in range(8)
    )
    answer = f'```json\n{{"one_line": "x", "principle_candidates": [{many}]}}\n```'
    writer, _, _, principles, _ = _writer(answer=answer)
    await writer(9, "r")
    cands = principles.added[0]["candidates"]
    assert len(cands) == 5 and {c.scope for c in cands} == {"all"}
