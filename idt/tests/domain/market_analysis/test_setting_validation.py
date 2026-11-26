"""설정 검증 (design §5.2)."""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest
from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.domain.market_analysis.setting_validation import SettingValidationPolicy

BASE = MarketAnalysisSetting.defaults()


def _errors(**changes):
    return SettingValidationPolicy.validate(dataclasses.replace(BASE, **changes))


def test_defaults_are_valid():
    assert _errors() == {}


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"round_times": ()}, "round_times"),
        ({"round_times": tuple(f"1{i}:00" for i in range(7))}, "round_times"),
        ({"round_times": ("25:00",)}, "round_times"),
        ({"round_times": ("9:00",)}, "round_times"),
        ({"round_times": ("10:00", "10:00")}, "round_times"),
        ({"max_per_round": 0}, "max_per_round"),
        ({"max_per_day": 201}, "max_per_day"),
        ({"max_per_round": 60, "max_per_day": 50}, "max_per_round"),
        ({"max_concurrent_stocks": 9}, "max_concurrent_stocks"),
        ({"max_concurrent_runs": 0}, "max_concurrent_runs"),
        ({"slot_count": 21}, "slot_count"),
        ({"signal_rules": ()}, "signal_rules"),
        ({"signal_rules": ("ma_cross", "moon_phase")}, "signal_rules"),
        ({"ranking_kinds": ("hot",)}, "ranking_kinds"),
        ({"ranking_kinds": (), "condition_seqs": ()}, "ranking_kinds"),
        ({"min_score_by_regime": {"bull": 6}}, "min_score_by_regime"),
        (
            {"min_score_by_regime": {**BASE.min_score_by_regime, "bear": 11}},
            "min_score_by_regime",
        ),
        ({"min_rr": Decimal("0.1")}, "min_rr"),
        ({"min_stop_pct": Decimal("8"), "max_stop_pct": Decimal("7")}, "min_stop_pct"),
    ],
)
def test_invalid_values_are_reported_per_field(changes, field):
    errors = _errors(**changes)
    assert field in errors and errors[field]


def test_condition_search_alone_is_enough():
    assert _errors(ranking_kinds=(), condition_seqs=("0",)) == {}


def test_moon_phase_message_names_the_rule():
    assert "moon_phase" in _errors(signal_rules=("moon_phase",))["signal_rules"]
