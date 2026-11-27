"""지수 확정 일봉 저장소 — `ma_index_daily` 읽기·덮어쓰기, `ma_market_regime` 읽기.

Design Ref: market-index-ytd-chart §3.3, §3.4 IndexDailyStore.
- 장중(provisional) 봉은 저장하지 않는다 (Plan FR-04).
- 같은 (지수, 거래일)은 덮어쓴다 — 동시 조회로 두 번 받아도 결과가 같다 (Plan FR-09).
- application 을 import 하지 않는다 (값 타입은 domain).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.market_analysis.index_chart import IndexBar
from src.infrastructure.market_analysis.models import (
    MaIndexDailyModel,
    MaMarketRegimeModel,
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _bar(row: MaIndexDailyModel) -> IndexBar:
    return IndexBar(
        index=row.index_code,
        day=row.trade_date,
        open=Decimal(str(row.open_price)),
        high=Decimal(str(row.high_price)),
        low=Decimal(str(row.low_price)),
        close=Decimal(str(row.close_price)),
    )


class IndexDailyRepository:
    def __init__(
        self, session_factory: Callable[[], Any], logger: LoggerInterface
    ) -> None:
        self._sf = session_factory
        self._logger = logger

    async def last_date(self, index: str, since: date, request_id: str) -> date | None:
        stmt = select(func.max(MaIndexDailyModel.trade_date)).where(
            MaIndexDailyModel.index_code == index,
            MaIndexDailyModel.trade_date >= since,
        )
        async with self._sf() as session:
            return (await session.execute(stmt)).scalar_one_or_none()

    async def upsert(self, bars: list[IndexBar], request_id: str) -> int:
        confirmed = [b for b in bars if not b.provisional]
        if not confirmed:
            return 0
        now = _now()
        async with self._sf() as session, session.begin():
            for b in confirmed:
                values = {
                    "open_price": b.open,
                    "high_price": b.high,
                    "low_price": b.low,
                    "close_price": b.close,
                    "created_at": now,
                }
                row = await session.get(MaIndexDailyModel, (b.index, b.day))
                if row is None:
                    session.add(
                        MaIndexDailyModel(
                            index_code=b.index, trade_date=b.day, **values
                        )
                    )
                else:
                    for key, value in values.items():
                        setattr(row, key, value)
        return len(confirmed)

    async def bars(
        self, index: str, start: date, end: date, request_id: str
    ) -> list[IndexBar]:
        stmt = (
            select(MaIndexDailyModel)
            .where(
                MaIndexDailyModel.index_code == index,
                MaIndexDailyModel.trade_date >= start,
                MaIndexDailyModel.trade_date <= end,
            )
            .order_by(MaIndexDailyModel.trade_date)
        )
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [_bar(r) for r in rows]

    async def regimes(
        self, start: date, end: date, request_id: str
    ) -> list[tuple[date, str]]:
        stmt = (
            select(MaMarketRegimeModel.trade_date, MaMarketRegimeModel.regime)
            .where(
                MaMarketRegimeModel.trade_date >= start,
                MaMarketRegimeModel.trade_date <= end,
            )
            .order_by(MaMarketRegimeModel.trade_date)
        )
        async with self._sf() as session:
            rows = (await session.execute(stmt)).all()
        return [(d, r) for d, r in rows]
