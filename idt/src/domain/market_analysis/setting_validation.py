"""설정 검증 — 값의 범위와 형식 (module-8, `PUT /settings`).

Design Ref: stock-analysis-agents §5.2 — 회차 시각 HH:MM 1~6개 · 상한 1~200 · 동시 1~8 ·
slot_count 1~20 · 규칙은 KIS 7종 안. 서버 id·실행 사용자가 실제로 쓸 수 있는지는
application 이 플랫폼 조회로 따로 확인한다(외부 의존이라 여기 두지 않는다).
결과는 필드 → 사유. 비어 있으면 통과.
"""

from __future__ import annotations

import re
from decimal import Decimal

from src.domain.market_analysis.setting import (
    DEFAULT_RANKING_KINDS,
    DEFAULT_SIGNAL_RULES,
    MarketAnalysisSetting,
)
from src.domain.market_analysis.value_objects import Regime

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
ALLOWED_RULES = frozenset(DEFAULT_SIGNAL_RULES)
ALLOWED_RANKINGS = frozenset(DEFAULT_RANKING_KINDS)


def _range(errors: dict[str, str], name: str, value: int, low: int, high: int) -> None:
    if not low <= value <= high:
        errors[name] = f"{low}~{high} 사이여야 합니다"


class SettingValidationPolicy:
    @staticmethod
    def validate(s: MarketAnalysisSetting) -> dict[str, str]:
        errors: dict[str, str] = {}
        times = list(s.round_times)
        if not 1 <= len(times) <= 6:
            errors["round_times"] = "회차 시각은 1~6개여야 합니다"
        elif any(not _HHMM.match(t) for t in times):
            errors["round_times"] = "회차 시각은 HH:MM 형식이어야 합니다"
        elif len(set(times)) != len(times):
            errors["round_times"] = "같은 회차 시각이 두 번 있습니다"

        _range(errors, "max_per_round", s.max_per_round, 1, 200)
        _range(errors, "max_per_day", s.max_per_day, 1, 200)
        if "max_per_round" not in errors and "max_per_day" not in errors:
            if s.max_per_round > s.max_per_day:
                errors["max_per_round"] = "회차 상한은 하루 상한보다 클 수 없습니다"
        _range(errors, "max_concurrent_stocks", s.max_concurrent_stocks, 1, 8)
        _range(errors, "max_concurrent_runs", s.max_concurrent_runs, 1, 8)
        _range(errors, "slot_count", s.slot_count, 1, 20)
        _range(errors, "ranking_limit", s.ranking_limit, 1, 100)
        _range(errors, "max_principles", s.max_principles, 0, 30)

        if not s.signal_rules:
            errors["signal_rules"] = "신호 규칙을 하나 이상 골라야 합니다"
        elif unknown := sorted(set(s.signal_rules) - ALLOWED_RULES):
            errors["signal_rules"] = f"모르는 규칙: {', '.join(unknown)}"
        if unknown := sorted(set(s.ranking_kinds) - ALLOWED_RANKINGS):
            errors["ranking_kinds"] = f"모르는 순위 종류: {', '.join(unknown)}"
        if not s.ranking_kinds and not s.condition_seqs:
            errors["ranking_kinds"] = "순위 종류나 조건검색 중 하나는 있어야 합니다"

        regimes = {r.value for r in Regime}
        scores = s.min_score_by_regime
        if set(scores) != regimes:
            errors["min_score_by_regime"] = "체제 5개의 최소 점수를 모두 정해야 합니다"
        elif any(not 1 <= int(v) <= 10 for v in scores.values()):
            errors["min_score_by_regime"] = "최소 점수는 1~10 사이여야 합니다"

        if not Decimal("0.5") <= s.min_rr <= Decimal("10"):
            errors["min_rr"] = "0.5~10 사이여야 합니다"
        if not Decimal("0.5") <= s.min_stop_pct <= Decimal("30"):
            errors["min_stop_pct"] = "0.5~30 사이여야 합니다"
        if not Decimal("0.5") <= s.max_stop_pct <= Decimal("30"):
            errors["max_stop_pct"] = "0.5~30 사이여야 합니다"
        if (
            "min_stop_pct" not in errors
            and "max_stop_pct" not in errors
            and s.min_stop_pct > s.max_stop_pct
        ):
            errors["min_stop_pct"] = "최소 손절폭이 최대 손절폭보다 큽니다"
        return errors
