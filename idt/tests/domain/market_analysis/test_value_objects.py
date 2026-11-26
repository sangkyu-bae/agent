"""market_analysis 값 객체 — stock-analysis-agents design §3.1."""

from src.domain.market_analysis.value_objects import (
    AgentRole,
    ItemStatus,
    Regime,
    RoundKind,
    RoundStatus,
    RoundTrigger,
)


def test_agent_roles_are_the_eleven_in_design():
    assert [r.value for r in AgentRole] == [
        "section_technical",
        "section_flow",
        "section_financial",
        "section_company",
        "section_news",
        "section_market",
        "strategy",
        "summary",
        "buy_judge",
        "sell_judge",
        "journal",
    ]


def test_section_roles_are_the_first_six():
    assert AgentRole.section_roles() == tuple(list(AgentRole)[:6])


def test_regime_order_from_strongest_bull():
    assert [r.value for r in Regime] == [
        "strong_bull",
        "bull",
        "neutral",
        "bear",
        "strong_bear",
    ]


def test_round_enums():
    assert {k.value for k in RoundKind} == {"intraday", "close"}
    assert {t.value for t in RoundTrigger} == {"auto", "manual"}
    assert {s.value for s in RoundStatus} == {
        "running",
        "done",
        "skipped",
        "failed",
        "abandoned",
    }
    assert {s.value for s in ItemStatus} == {
        "queued",
        "analyzing",
        "done",
        "failed",
        "over_cap",
        "duplicate",
        "held",
    }


def test_enums_compare_with_plain_strings():
    # DB 에 문자열로 저장한 값과 바로 비교할 수 있어야 한다
    assert AgentRole.BUY_JUDGE == "buy_judge"
    assert RoundStatus("skipped") is RoundStatus.SKIPPED
