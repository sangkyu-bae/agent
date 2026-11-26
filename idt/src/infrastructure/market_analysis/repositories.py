"""시장 분석 저장소 — module-1: 설정 조회.

Design Ref: stock-analysis-agents §3.3 ma_setting. 행이 없으면 기본값을 돌려준다
(V101 이 기본 행을 넣지만, 테스트·빈 DB 에서도 모듈이 동작해야 한다).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.infrastructure.market_analysis.models import MaSettingModel

SETTING_ROW_ID = 1


def _to_setting(row: MaSettingModel) -> MarketAnalysisSetting:
    return MarketAnalysisSetting(
        enabled=bool(row.enabled),
        round_times=tuple(row.round_times or ()),
        max_per_round=row.max_per_round,
        max_per_day=row.max_per_day,
        max_concurrent_stocks=row.max_concurrent_stocks,
        max_concurrent_runs=row.max_concurrent_runs,
        signal_rules=tuple(row.signal_rules or ()),
        rule_params=row.rule_params,
        ranking_kinds=tuple(row.ranking_kinds or ()),
        ranking_limit=row.ranking_limit,
        condition_seqs=tuple(str(s) for s in (row.condition_seqs or ())),
        intraday_entry_allowed=bool(row.intraday_entry_allowed),
        slot_count=row.slot_count,
        min_score_by_regime={
            k: int(v) for k, v in (row.min_score_by_regime or {}).items()
        },
        min_rr=Decimal(str(row.min_rr)),
        max_stop_pct=Decimal(str(row.max_stop_pct)),
        min_stop_pct=Decimal(str(row.min_stop_pct)),
        max_principles=row.max_principles,
        principle_auto_activate=bool(row.principle_auto_activate),
        run_as_user_id=row.run_as_user_id,
        kis_server_id=row.kis_server_id,
        dart_server_id=row.dart_server_id,
        perplexity_server_id=row.perplexity_server_id,
    )


class SettingRepository:
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def get(self, request_id: str) -> MarketAnalysisSetting:
        try:
            row = (
                await self._session.execute(
                    select(MaSettingModel).where(MaSettingModel.id == SETTING_ROW_ID)
                )
            ).scalar_one_or_none()
        except Exception as e:
            self._logger.error(
                "market_analysis setting read failed",
                exception=e,
                request_id=request_id,
            )
            raise
        if row is None:
            return MarketAnalysisSetting.defaults()
        return _to_setting(row)


def _setting_values(s: MarketAnalysisSetting) -> dict:
    return {
        "enabled": s.enabled,
        "round_times": list(s.round_times),
        "max_per_round": s.max_per_round,
        "max_per_day": s.max_per_day,
        "max_concurrent_stocks": s.max_concurrent_stocks,
        "max_concurrent_runs": s.max_concurrent_runs,
        "signal_rules": list(s.signal_rules),
        "rule_params": s.rule_params,
        "ranking_kinds": list(s.ranking_kinds),
        "ranking_limit": s.ranking_limit,
        "condition_seqs": list(s.condition_seqs),
        "intraday_entry_allowed": s.intraday_entry_allowed,
        "slot_count": s.slot_count,
        "min_score_by_regime": dict(s.min_score_by_regime),
        "min_rr": s.min_rr,
        "max_stop_pct": s.max_stop_pct,
        "min_stop_pct": s.min_stop_pct,
        "max_principles": s.max_principles,
        "principle_auto_activate": s.principle_auto_activate,
        "run_as_user_id": s.run_as_user_id,
        "kis_server_id": s.kis_server_id,
        "dart_server_id": s.dart_server_id,
        "perplexity_server_id": s.perplexity_server_id,
    }


class SessionSettingWriter:
    """application.ports.SettingWriter —
    module-8. 단일 행(id=1)을 덮어쓴다(없으면 만든다)."""

    def __init__(
        self, session_factory: Callable[[], Any], logger: LoggerInterface
    ) -> None:
        self._sf = session_factory
        self._logger = logger

    async def save(
        self, setting: MarketAnalysisSetting, *, updated_by: str, request_id: str
    ) -> None:
        values = {
            **_setting_values(setting),
            "updated_by": updated_by[:100],
            "updated_at": datetime.now(UTC).replace(tzinfo=None),
        }
        async with self._sf() as session, session.begin():
            row = await session.get(MaSettingModel, SETTING_ROW_ID)
            if row is None:
                session.add(MaSettingModel(id=SETTING_ROW_ID, **values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)
