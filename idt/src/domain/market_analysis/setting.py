"""시장 분석 모듈 설정 (ma_setting 단일 행).

Design Ref: stock-analysis-agents §1.3(Plan Q1~Q7 기본값), §3.3, §5.2.
env 가 아니라 DB 에 두고 화면에서 바꾼다 (Plan §8.3). 행이 없으면 defaults() 를 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

# mcp-kis-server scan_signals 규칙 7종 — D6: 기본은 전부
DEFAULT_SIGNAL_RULES: tuple[str, ...] = (
    "ma_cross",
    "rsi_threshold",
    "bollinger_break",
    "macd_cross",
    "volume_spike",
    "gap",
    "closing_strength",
)
DEFAULT_RANKING_KINDS: tuple[str, ...] = ("volume", "fluctuation", "volume_power")
DEFAULT_ROUND_TIMES: tuple[str, ...] = ("10:00", "14:00", "18:10")


def _default_min_scores() -> dict[str, int]:
    return {"strong_bull": 5, "bull": 6, "neutral": 6, "bear": 7, "strong_bear": 8}


@dataclass(frozen=True)
class MarketAnalysisSetting:
    # Plan FR-01: 자동 분석 스위치 — 꺼진 채로 시작한다
    enabled: bool = False
    round_times: tuple[str, ...] = DEFAULT_ROUND_TIMES
    # Plan FR-02: 비용 사고 방지 상한 (M8 실측 후 조정)
    max_per_round: int = 20
    max_per_day: int = 50
    max_concurrent_stocks: int = 2
    max_concurrent_runs: int = 4
    signal_rules: tuple[str, ...] = DEFAULT_SIGNAL_RULES
    rule_params: dict[str, Any] | None = None
    ranking_kinds: tuple[str, ...] = DEFAULT_RANKING_KINDS
    ranking_limit: int = 30
    condition_seqs: tuple[str, ...] = ()
    intraday_entry_allowed: bool = True
    slot_count: int = 10
    min_score_by_regime: dict[str, int] = field(default_factory=_default_min_scores)
    min_rr: Decimal = Decimal("2.00")
    max_stop_pct: Decimal = Decimal("7.00")
    min_stop_pct: Decimal = Decimal("2.00")
    max_principles: int = 10
    # DD9: 원칙 후보는 비활성으로 저장, 운영자가 켠다
    principle_auto_activate: bool = False
    run_as_user_id: str | None = None
    kis_server_id: str | None = None
    dart_server_id: str | None = None
    perplexity_server_id: str | None = None

    @classmethod
    def defaults(cls) -> MarketAnalysisSetting:
        return cls()
