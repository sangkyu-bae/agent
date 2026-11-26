"""가상 계좌 저장소 — 포지션 · 판단 · 체제 · 성과 스냅샷 (module-6).

Design Ref: stock-analysis-agents §3.3.
application.ports 의 PositionStore · DecisionStore ·
RegimeStore · HeldReader 를 구조적 타이핑으로 맞춘다(application 을 import 하지 않는다).
요청 밖(ticker)에서 쓰므로 동작마다 세션 팩토리로 짧은 트랜잭션을 연다.
일자별 표(ma_market_regime · ma_equity_snapshot)는 같은 날 다시 쓰면 덮어쓴다.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.market_analysis.account import (
    ClosedTrade,
    DecisionDraft,
    ExitReason,
    Position,
    RegimeResult,
)
from src.infrastructure.market_analysis.models import (
    MaDecisionModel,
    MaEquitySnapshotModel,
    MaMarketRegimeModel,
    MaPositionModel,
)

OPEN = "open"
CLOSED = "closed"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _dec(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


class PositionRepository:
    def __init__(
        self, session_factory: Callable[[], Any], logger: LoggerInterface
    ) -> None:
        self._sf = session_factory
        self._logger = logger

    async def open_positions(self, request_id: str) -> list[Position]:
        stmt = (
            select(MaPositionModel, MaDecisionModel.rationale)
            .outerjoin(
                MaDecisionModel, MaDecisionModel.id == MaPositionModel.buy_decision_id
            )
            .where(MaPositionModel.status == OPEN)
            .order_by(MaPositionModel.entry_at, MaPositionModel.id)
        )
        async with self._sf() as session:
            rows = (await session.execute(stmt)).all()
        return [
            Position(
                id=int(p.id),
                symbol=p.symbol,
                name=p.name,
                sector=p.sector,
                slot_weight=Decimal(str(p.slot_weight)),
                entry_price=Decimal(str(p.entry_price)),
                entry_at=p.entry_at,
                target_price=Decimal(str(p.target_price)),
                stop_loss=Decimal(str(p.stop_loss)),
                buy_decision_id=p.buy_decision_id,
                buy_rationale=rationale,
            )
            for p, rationale in rows
        ]

    async def held_symbols(self, request_id: str) -> set[str]:
        async with self._sf() as session:
            rows = await session.execute(
                select(MaPositionModel.symbol).where(MaPositionModel.status == OPEN)
            )
            return {row[0] for row in rows.all()}

    async def open_position(
        self,
        *,
        symbol: str,
        name: str | None,
        sector: str | None,
        entry_price: Decimal,
        entry_at: datetime,
        target_price: Decimal,
        stop_loss: Decimal,
        buy_decision_id: int | None,
        request_id: str,
    ) -> int:
        now = _now()
        row = MaPositionModel(
            symbol=symbol,
            name=name,
            sector=(sector or None) and sector[:100],
            status=OPEN,
            slot_weight=Decimal("1.000"),
            entry_price=entry_price,
            entry_at=entry_at,
            target_price=target_price,
            stop_loss=stop_loss,
            buy_decision_id=buy_decision_id,
            created_at=now,
            updated_at=now,
        )
        async with self._sf() as session, session.begin():
            session.add(row)
            await session.flush()
            return int(row.id)

    async def close_position(
        self,
        *,
        position_id: int,
        exit_price: Decimal,
        exit_at: datetime,
        reason: ExitReason,
        profit_rate: Decimal,
        holding_days: int,
        request_id: str,
    ) -> None:
        stmt = (
            update(MaPositionModel)
            .where(MaPositionModel.id == position_id, MaPositionModel.status == OPEN)
            .values(
                status=CLOSED,
                exit_price=exit_price,
                exit_at=exit_at,
                exit_reason=reason.value,
                profit_rate=profit_rate,
                holding_days=holding_days,
                updated_at=_now(),
            )
        )
        async with self._sf() as session, session.begin():
            await session.execute(stmt)

    async def adjust_levels(
        self,
        *,
        position_id: int,
        target_price: Decimal,
        stop_loss: Decimal,
        request_id: str,
    ) -> None:
        stmt = (
            update(MaPositionModel)
            .where(MaPositionModel.id == position_id, MaPositionModel.status == OPEN)
            .values(target_price=target_price, stop_loss=stop_loss, updated_at=_now())
        )
        async with self._sf() as session, session.begin():
            await session.execute(stmt)

    async def closed_trades(self, request_id: str) -> list[ClosedTrade]:
        stmt = select(
            MaPositionModel.profit_rate,
            MaPositionModel.slot_weight,
            MaPositionModel.holding_days,
        ).where(MaPositionModel.status == CLOSED)
        async with self._sf() as session:
            rows = (await session.execute(stmt)).all()
        return [
            ClosedTrade(
                profit_rate=Decimal(str(rate)),
                slot_weight=Decimal(str(weight)),
                holding_days=int(days or 0),
            )
            for rate, weight, days in rows
            if rate is not None
        ]


class DecisionRepository:
    def __init__(
        self, session_factory: Callable[[], Any], logger: LoggerInterface
    ) -> None:
        self._sf = session_factory
        self._logger = logger

    async def add(self, draft: DecisionDraft, request_id: str) -> int:
        row = MaDecisionModel(
            kind=draft.kind,
            symbol=draft.symbol,
            name=draft.name,
            report_id=draft.report_id,
            position_id=draft.position_id,
            score=draft.score,
            decision=draft.decision,
            target_price=draft.target_price,
            stop_loss=draft.stop_loss,
            investment_period=draft.investment_period,
            sector=(draft.sector or None) and draft.sector[:100],
            confidence=draft.confidence,
            rationale=draft.rationale,
            skip_reason=draft.skip_reason,
            gate=draft.gate,
            principles_used=list(draft.principles_used) or None,
            price_at_decision=draft.price_at_decision,
            regime=draft.regime,
            provisional=draft.provisional,
            run_id=draft.run_id,
            created_at=draft.created_at,
        )
        async with self._sf() as session, session.begin():
            session.add(row)
            await session.flush()
            return int(row.id)

    async def link_position(
        self, *, decision_id: int, position_id: int, request_id: str
    ) -> None:
        stmt = (
            update(MaDecisionModel)
            .where(MaDecisionModel.id == decision_id)
            .values(position_id=position_id)
        )
        async with self._sf() as session, session.begin():
            await session.execute(stmt)

    async def mark_entry_failed(
        self, *, decision_id: int, reason: str, request_id: str
    ) -> None:
        """중간 점검 M3: 포지션을 못 만든 enter 판단을 skip 으로 되돌린다."""
        stmt = (
            update(MaDecisionModel)
            .where(
                MaDecisionModel.id == decision_id, MaDecisionModel.decision == "enter"
            )
            .values(decision="skip", skip_reason=reason[:1000])
        )
        async with self._sf() as session, session.begin():
            await session.execute(stmt)


class RegimeRepository:
    def __init__(
        self, session_factory: Callable[[], Any], logger: LoggerInterface
    ) -> None:
        self._sf = session_factory
        self._logger = logger

    async def save_regime(
        self,
        *,
        trade_date: date,
        result: RegimeResult,
        kosdaq_close: Decimal | None,
        bars: int,
        request_id: str,
    ) -> None:
        values = {
            "kospi_close": result.close,
            "kosdaq_close": kosdaq_close,
            "kospi_ma20": result.ma20,
            "kospi_ma60": result.ma60,
            "regime": result.regime.value,
            "basis": {
                "r20": None if result.r20 is None else str(result.r20),
                "bars": bars,
                "insufficient": result.insufficient,
            },
            "created_at": _now(),
        }
        async with self._sf() as session, session.begin():
            row = await session.get(MaMarketRegimeModel, trade_date)
            if row is None:
                session.add(MaMarketRegimeModel(trade_date=trade_date, **values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)

    async def first_closes(
        self, request_id: str
    ) -> tuple[Decimal | None, Decimal | None] | None:
        stmt = (
            select(MaMarketRegimeModel.kospi_close, MaMarketRegimeModel.kosdaq_close)
            .order_by(MaMarketRegimeModel.trade_date)
            .limit(1)
        )
        async with self._sf() as session:
            row = (await session.execute(stmt)).first()
        return None if row is None else (_dec(row[0]), _dec(row[1]))

    async def save_snapshot(
        self,
        *,
        trade_date: date,
        realized_cum_rate: Decimal,
        open_positions: int,
        used_slots: Decimal,
        kospi_cum_rate: Decimal | None,
        kosdaq_cum_rate: Decimal | None,
        request_id: str,
    ) -> None:
        values = {
            "realized_cum_rate": realized_cum_rate,
            "open_positions": open_positions,
            "used_slots": used_slots,
            "kospi_cum_rate": kospi_cum_rate,
            "kosdaq_cum_rate": kosdaq_cum_rate,
            "created_at": _now(),
        }
        async with self._sf() as session, session.begin():
            row = await session.get(MaEquitySnapshotModel, trade_date)
            if row is None:
                session.add(MaEquitySnapshotModel(trade_date=trade_date, **values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)
