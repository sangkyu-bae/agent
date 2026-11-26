"""모듈 설정 기본값 — stock-analysis-agents design §1.3, §3.3, §5.2."""

from decimal import Decimal

from src.domain.market_analysis.setting import (
    DEFAULT_SIGNAL_RULES,
    MarketAnalysisSetting,
)


def test_defaults_match_design():
    s = MarketAnalysisSetting.defaults()
    # D6·FR-01: 자동 분석은 꺼진 채로 시작한다 — 운영자가 켠다
    assert s.enabled is False
    assert s.round_times == ("10:00", "14:00", "18:10")
    assert (s.max_per_round, s.max_per_day) == (20, 50)
    assert (s.max_concurrent_stocks, s.max_concurrent_runs) == (2, 4)
    assert s.signal_rules == DEFAULT_SIGNAL_RULES
    assert s.ranking_kinds == ("volume", "fluctuation", "volume_power")
    assert s.ranking_limit == 30
    assert s.condition_seqs == ()
    assert s.intraday_entry_allowed is True
    assert s.slot_count == 10
    assert s.min_score_by_regime == {
        "strong_bull": 5,
        "bull": 6,
        "neutral": 6,
        "bear": 7,
        "strong_bear": 8,
    }
    assert s.min_rr == Decimal("2.00")
    assert (s.min_stop_pct, s.max_stop_pct) == (Decimal("2.00"), Decimal("7.00"))
    assert s.max_principles == 10
    assert s.principle_auto_activate is False  # DD9
    assert s.run_as_user_id is None
    assert (s.kis_server_id, s.dart_server_id, s.perplexity_server_id) == (
        None,
        None,
        None,
    )


def test_default_signal_rules_are_the_seven_kis_rules():
    assert DEFAULT_SIGNAL_RULES == (
        "ma_cross",
        "rsi_threshold",
        "bollinger_break",
        "macd_cross",
        "volume_spike",
        "gap",
        "closing_strength",
    )


def test_setting_is_immutable():
    import dataclasses

    import pytest

    s = MarketAnalysisSetting.defaults()
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.enabled = True  # type: ignore[misc]
