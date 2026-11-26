"""성과 스냅샷 — close 회차 ⑧.

Design Ref: stock-analysis-agents §2.2 ⑧, §6 PerformancePolicy.
누적 실현 수익률은 청산 건만 슬롯 비중으로 더한다(복리·평가손익 아님).
지수 누적 수익률의 기준은 가장 이른 체제 기록일의
종가다 — 계좌가 처음 돈 날부터 비교한다.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from src.application.market_analysis.ports import PositionStore, RegimeStore
from src.application.market_analysis.regime import MarketSnapshot
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.market_analysis.account import PerformancePolicy
from src.domain.market_analysis.setting import MarketAnalysisSetting


def _cum(base: Decimal | None, now: Decimal | None) -> Decimal | None:
    if base is None or now is None or base <= 0:
        return None
    return ((now / base - 1) * 100).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


class PerformanceRecorder:
    def __init__(
        self,
        *,
        positions: PositionStore,
        regimes: RegimeStore,
        logger: LoggerInterface,
    ) -> None:
        self._positions = positions
        self._regimes = regimes
        self._logger = logger

    async def record(
        self,
        *,
        trade_date: date,
        snapshot: MarketSnapshot,
        setting: MarketAnalysisSetting,
        request_id: str,
    ) -> None:
        closed = await self._positions.closed_trades(request_id)
        held = await self._positions.open_positions(request_id)
        summary = PerformancePolicy.summary(
            [(t.profit_rate, t.slot_weight) for t in closed],
            slot_count=setting.slot_count,
            holding_days=[t.holding_days for t in closed],
        )
        base = await self._regimes.first_closes(request_id)
        kospi_base, kosdaq_base = base if base is not None else (None, None)
        await self._regimes.save_snapshot(
            trade_date=trade_date,
            realized_cum_rate=summary.realized_cum_rate,
            open_positions=len(held),
            used_slots=sum((p.slot_weight for p in held), Decimal("0")),
            kospi_cum_rate=_cum(kospi_base, snapshot.kospi_close),
            kosdaq_cum_rate=_cum(kosdaq_base, snapshot.kosdaq_close),
            request_id=request_id,
        )
