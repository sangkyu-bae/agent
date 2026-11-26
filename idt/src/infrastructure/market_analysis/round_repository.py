"""회차 저장소 · 요청 밖 설정 조회 (module-5). 보유 종목은 account_repository.

Design Ref: stock-analysis-agents §3.3, DD6. 회차 선점은
ma_round UNIQUE(trade_date, slot, run_trigger) 위반을
잡아 None 으로 돌려준다 — 다중 인스턴스·다음 틱이 같은 회차를 두 번 돌리지 않는다(U14).
모든 동작은 세션 팩토리로 짧은 트랜잭션을 연다(요청 밖 ticker).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.market_analysis.round import RoundCounts, RoundItemDraft
from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.domain.market_analysis.value_objects import (
    ItemStatus,
    RoundKind,
    RoundStatus,
    RoundTrigger,
)
from src.infrastructure.market_analysis.models import (
    MaReportModel,
    MaRoundItemModel,
    MaRoundModel,
)
from src.infrastructure.market_analysis.repositories import SettingRepository

# 하루 1회 분석(FR-04)에서 "이미 분석함" 으로
# 보는 상태 — failed 는 다음 회차에 다시 시도한다
_ANALYZED = (ItemStatus.DONE.value, ItemStatus.ANALYZING.value, ItemStatus.QUEUED.value)
_PENDING = (ItemStatus.QUEUED.value, ItemStatus.ANALYZING.value)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class RoundRepository:
    def __init__(
        self, session_factory: Callable[[], Any], logger: LoggerInterface
    ) -> None:
        self._sf = session_factory
        self._logger = logger

    async def try_claim(
        self,
        *,
        trade_date: date,
        slot: str,
        kind: RoundKind,
        trigger: RoundTrigger,
        request_id: str,
    ) -> int | None:
        row = MaRoundModel(
            trade_date=trade_date,
            slot=slot,
            kind=kind.value,
            run_trigger=trigger.value,
            status=RoundStatus.RUNNING.value,
            started_at=_now(),
        )
        try:
            async with self._sf() as session, session.begin():
                session.add(row)
                await session.flush()
                return int(row.id)
        except IntegrityError:
            return None

    async def any_running(self, *, exclude_id: int | None, request_id: str) -> bool:
        stmt = select(MaRoundModel.id).where(
            MaRoundModel.status == RoundStatus.RUNNING.value
        )
        if exclude_id is not None:
            stmt = stmt.where(MaRoundModel.id != exclude_id)
        async with self._sf() as session:
            return (await session.execute(stmt.limit(1))).first() is not None

    async def skip(self, *, round_id: int, reason: str, request_id: str) -> None:
        async with self._sf() as session, session.begin():
            await session.execute(
                update(MaRoundModel)
                .where(MaRoundModel.id == round_id)
                .values(
                    status=RoundStatus.SKIPPED.value,
                    skip_reason=str(reason),
                    finished_at=_now(),
                )
            )

    async def add_items(
        self, *, round_id: int, items: list[RoundItemDraft], request_id: str
    ) -> dict[str, int]:
        rows = [
            MaRoundItemModel(
                round_id=round_id,
                symbol=item.symbol,
                name=item.name,
                signals=list(item.signals),
                status=item.status,
                tokens=0,
                cost_usd=Decimal("0"),
                created_at=_now(),
            )
            for item in items
        ]
        async with self._sf() as session, session.begin():
            session.add_all(rows)
            await session.flush()
            return {row.symbol: int(row.id) for row in rows}

    async def update_item(
        self,
        *,
        item_id: int,
        status: ItemStatus,
        report_id: int | None = None,
        tokens: int = 0,
        cost_usd: Decimal = Decimal("0"),
        error: str | None = None,
        request_id: str,
    ) -> None:
        values: dict[str, Any] = {
            "status": status.value,
            "tokens": tokens,
            "cost_usd": cost_usd,
        }
        if report_id is not None:
            values["report_id"] = report_id
        if error is not None:
            values["error"] = error[:500]
        async with self._sf() as session, session.begin():
            await session.execute(
                update(MaRoundItemModel)
                .where(MaRoundItemModel.id == item_id)
                .values(**values)
            )

    async def finish_round(
        self,
        *,
        round_id: int,
        status: RoundStatus,
        counts: RoundCounts,
        error: str | None,
        request_id: str,
    ) -> None:
        async with self._sf() as session, session.begin():
            await session.execute(
                update(MaRoundModel)
                .where(MaRoundModel.id == round_id)
                .values(
                    status=status.value,
                    candidates=counts.candidates,
                    signaled=counts.signaled,
                    analyzed=counts.analyzed,
                    over_cap=counts.over_cap,
                    failed=counts.failed,
                    total_tokens=counts.tokens,
                    total_cost_usd=counts.cost_usd,
                    error=error,
                    finished_at=_now(),
                )
            )

    async def analyzed_symbols(self, *, trade_date: date, request_id: str) -> set[str]:
        stmt = (
            select(MaRoundItemModel.symbol)
            .join(MaRoundModel, MaRoundModel.id == MaRoundItemModel.round_id)
            .where(MaRoundModel.trade_date == trade_date)
            .where(MaRoundItemModel.status.in_(_ANALYZED))
        )
        async with self._sf() as session:
            return {row[0] for row in (await session.execute(stmt)).all()}

    async def abandon_running(self, request_id: str) -> int:
        async with self._sf() as session, session.begin():
            ids = [
                row[0]
                for row in (
                    await session.execute(
                        select(MaRoundModel.id).where(
                            MaRoundModel.status == RoundStatus.RUNNING.value
                        )
                    )
                ).all()
            ]
            if not ids:
                return 0
            await session.execute(
                update(MaRoundModel)
                .where(MaRoundModel.id.in_(ids))
                .values(status=RoundStatus.ABANDONED.value, finished_at=_now())
            )
            await session.execute(
                update(MaRoundItemModel)
                .where(MaRoundItemModel.round_id.in_(ids))
                .where(MaRoundItemModel.status.in_(_PENDING))
                .values(status=ItemStatus.FAILED.value, error="ABANDONED")
            )
            # 중간 점검 I2: 그 회차에서 쓰다 만 리포트도 running 으로 남기지 않는다
            await session.execute(
                update(MaReportModel)
                .where(MaReportModel.round_id.in_(ids))
                .where(MaReportModel.status == "running")
                .values(status="failed")
            )
            return len(ids)


class SessionSettingReader:
    """application.ports.SettingReader — 요청
    밖(ticker)에서 매번 최신 설정을 읽는다 (스위치 즉시 반영)."""

    def __init__(
        self, session_factory: Callable[[], Any], logger: LoggerInterface
    ) -> None:
        self._sf = session_factory
        self._logger = logger

    async def get(self, request_id: str) -> MarketAnalysisSetting:
        async with self._sf() as session:
            return await SettingRepository(session, self._logger).get(request_id)
