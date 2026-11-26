"""조회 저장소 — 화면용 읽기 (module-8, application.ports.QueryStore).

Design Ref: stock-analysis-agents §5.1, §5.2. 시각은 UTC ISO(+00:00), 거래일은
YYYY-MM-DD, 금액·비율은 float 로 내보낸다. 근거 payload 는 화면에서 펼쳐 보는
용도라 항목당 20,000자에서 자른다.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.market_analysis.principle import PRIORITY_RANK
from src.infrastructure.market_analysis.models import (
    MaDecisionModel,
    MaEquitySnapshotModel,
    MaEvidenceModel,
    MaJournalModel,
    MaMarketRegimeModel,
    MaPositionModel,
    MaPrincipleModel,
    MaReportModel,
    MaReportSectionModel,
    MaRoundItemModel,
    MaRoundModel,
)

EVIDENCE_MAX = 20_000


def _iso(dt: datetime | None) -> str | None:
    return None if dt is None else dt.replace(tzinfo=UTC).isoformat()


def _day(d: date | None) -> str | None:
    return None if d is None else d.isoformat()


def _num(value: Any) -> float | None:
    return None if value is None else float(Decimal(str(value)))


def _rules(signals: Any) -> list[str]:
    if not isinstance(signals, list):
        return []
    return [
        str(s.get("rule")) for s in signals if isinstance(s, dict) and s.get("rule")
    ]


def _position(p: MaPositionModel) -> dict[str, Any]:
    return {
        "id": int(p.id),
        "symbol": p.symbol,
        "name": p.name,
        "sector": p.sector,
        "status": p.status,
        "slot_weight": _num(p.slot_weight),
        "entry_price": _num(p.entry_price),
        "entry_at": _iso(p.entry_at),
        "target_price": _num(p.target_price),
        "stop_loss": _num(p.stop_loss),
        "exit_price": _num(p.exit_price),
        "exit_at": _iso(p.exit_at),
        "exit_reason": p.exit_reason,
        "profit_rate": _num(p.profit_rate),
        "holding_days": p.holding_days,
        "buy_decision_id": p.buy_decision_id,
    }


def _decision(d: MaDecisionModel) -> dict[str, Any]:
    return {
        "id": int(d.id),
        "kind": d.kind,
        "symbol": d.symbol,
        "name": d.name,
        "decision": d.decision,
        "score": d.score,
        "confidence": d.confidence,
        "target_price": _num(d.target_price),
        "stop_loss": _num(d.stop_loss),
        "investment_period": d.investment_period,
        "sector": d.sector,
        "rationale": d.rationale,
        "skip_reason": d.skip_reason,
        "gate": d.gate,
        "principles_used": d.principles_used or [],
        "price_at_decision": _num(d.price_at_decision),
        "regime": d.regime,
        "provisional": bool(d.provisional),
        "report_id": d.report_id,
        "position_id": d.position_id,
        "run_id": d.run_id,
        "created_at": _iso(d.created_at),
    }


def _journal(j: MaJournalModel) -> dict[str, Any]:
    return {
        "id": int(j.id),
        "position_id": j.position_id,
        "one_line": j.one_line,
        "situation": j.situation,
        "evaluation": j.evaluation,
        "lessons": j.lessons or [],
        "tags": j.tags or [],
        "raw_answer": j.raw_answer,
        "created_at": _iso(j.created_at),
    }


def _report(r: MaReportModel) -> dict[str, Any]:
    return {
        "id": int(r.id),
        "symbol": r.symbol,
        "name": r.name,
        "trade_date": _day(r.trade_date),
        "round_id": r.round_id,
        "provisional": bool(r.provisional),
        "signals": r.signals or [],
        "regime": r.regime,
        "status": r.status,
        "summary": r.summary,
        "tokens": int(r.tokens or 0),
        "cost_usd": _num(r.cost_usd),
        "created_at": _iso(r.created_at),
    }


def _round(r: MaRoundModel) -> dict[str, Any]:
    return {
        "id": int(r.id),
        "trade_date": _day(r.trade_date),
        "slot": r.slot,
        "kind": r.kind,
        "trigger": r.run_trigger,
        "status": r.status,
        "skip_reason": r.skip_reason,
        "candidates": r.candidates,
        "signaled": r.signaled,
        "analyzed": r.analyzed,
        "over_cap": r.over_cap,
        "failed": r.failed,
        "tokens": int(r.total_tokens or 0),
        "cost_usd": _num(r.total_cost_usd),
        "error": r.error,
        "started_at": _iso(r.started_at),
        "finished_at": _iso(r.finished_at),
    }


class QueryRepository:
    def __init__(
        self, session_factory: Callable[[], Any], logger: LoggerInterface
    ) -> None:
        self._sf = session_factory
        self._logger = logger

    async def _page(self, stmt: Any, page: int, size: int) -> tuple[list[Any], int]:
        count = select(func.count()).select_from(stmt.order_by(None).subquery())
        async with self._sf() as session:
            total = int((await session.execute(count)).scalar_one())
            rows = (
                (await session.execute(stmt.offset((page - 1) * size).limit(size)))
                .scalars()
                .all()
            )
        return list(rows), total

    # ── 대시보드 재료 ──────────────────────────────────────────────────────

    async def closed_trades(self, request_id: str) -> list[dict[str, Any]]:
        stmt = (
            select(
                MaPositionModel.profit_rate,
                MaPositionModel.slot_weight,
                MaPositionModel.holding_days,
                MaReportModel.signals,
            )
            .outerjoin(
                MaDecisionModel, MaDecisionModel.id == MaPositionModel.buy_decision_id
            )
            .outerjoin(MaReportModel, MaReportModel.id == MaDecisionModel.report_id)
            .where(MaPositionModel.status == "closed")
        )
        async with self._sf() as session:
            rows = (await session.execute(stmt)).all()
        return [
            {
                "profit_rate": _num(rate) or 0.0,
                "slot_weight": _num(weight) or 1.0,
                "holding_days": int(days or 0),
                "rules": _rules(signals),
            }
            for rate, weight, days, signals in rows
            if rate is not None
        ]

    async def open_summary(self, request_id: str) -> dict[str, Any]:
        stmt = select(
            func.count(MaPositionModel.id), func.sum(MaPositionModel.slot_weight)
        ).where(MaPositionModel.status == "open")
        async with self._sf() as session:
            count, used = (await session.execute(stmt)).one()
        return {"open_positions": int(count or 0), "used_slots": _num(used) or 0.0}

    async def equity_series(self, limit: int, request_id: str) -> list[dict[str, Any]]:
        stmt = (
            select(MaEquitySnapshotModel)
            .order_by(MaEquitySnapshotModel.trade_date.desc())
            .limit(limit)
        )
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [
            {
                "date": _day(r.trade_date),
                "portfolio": _num(r.realized_cum_rate),
                "kospi": _num(r.kospi_cum_rate),
                "kosdaq": _num(r.kosdaq_cum_rate),
                "open_positions": r.open_positions,
            }
            for r in reversed(rows)
        ]

    async def latest_regime(self, request_id: str) -> dict[str, Any] | None:
        stmt = (
            select(MaMarketRegimeModel)
            .order_by(MaMarketRegimeModel.trade_date.desc())
            .limit(1)
        )
        async with self._sf() as session:
            r = (await session.execute(stmt)).scalars().first()
        if r is None:
            return None
        return {
            "date": _day(r.trade_date),
            "value": r.regime,
            "kospi_close": _num(r.kospi_close),
            "kosdaq_close": _num(r.kosdaq_close),
            "basis": r.basis,
        }

    async def last_round(self, request_id: str) -> dict[str, Any] | None:
        stmt = select(MaRoundModel).order_by(MaRoundModel.started_at.desc()).limit(1)
        async with self._sf() as session:
            r = (await session.execute(stmt)).scalars().first()
        return None if r is None else _round(r)

    # ── 목록·상세 ─────────────────────────────────────────────────────────

    async def list_positions(
        self, *, status: str, page: int, size: int, request_id: str
    ) -> tuple[list[dict[str, Any]], int]:
        order = (
            MaPositionModel.exit_at.desc()
            if status == "closed"
            else MaPositionModel.entry_at.desc()
        )
        stmt = (
            select(MaPositionModel)
            .where(MaPositionModel.status == status)
            .order_by(order, MaPositionModel.id.desc())
        )
        rows, total = await self._page(stmt, page, size)
        return [_position(p) for p in rows], total

    async def position_detail(
        self, position_id: int, request_id: str
    ) -> dict[str, Any] | None:
        async with self._sf() as session:
            p = await session.get(MaPositionModel, position_id)
            if p is None:
                return None
            decisions = (
                (
                    await session.execute(
                        select(MaDecisionModel)
                        .where(MaDecisionModel.position_id == position_id)
                        .order_by(MaDecisionModel.created_at, MaDecisionModel.id)
                    )
                )
                .scalars()
                .all()
            )
            journal = (
                (
                    await session.execute(
                        select(MaJournalModel).where(
                            MaJournalModel.position_id == position_id
                        )
                    )
                )
                .scalars()
                .first()
            )
        buy = next((d for d in decisions if d.kind == "buy"), None)
        return {
            **_position(p),
            "buy_decision": None if buy is None else _decision(buy),
            "sell_decisions": [_decision(d) for d in decisions if d.kind == "sell"],
            "journal": None if journal is None else _journal(journal),
            "report_id": None if buy is None else buy.report_id,
        }

    async def list_decisions(
        self, *, kind: str, decision: str | None, page: int, size: int, request_id: str
    ) -> tuple[list[dict[str, Any]], int]:
        stmt = select(MaDecisionModel).where(MaDecisionModel.kind == kind)
        if decision:
            stmt = stmt.where(MaDecisionModel.decision == decision)
        stmt = stmt.order_by(
            MaDecisionModel.created_at.desc(), MaDecisionModel.id.desc()
        )
        rows, total = await self._page(stmt, page, size)
        return [_decision(d) for d in rows], total

    async def list_reports(
        self,
        *,
        symbol: str | None,
        trade_date: date | None,
        page: int,
        size: int,
        request_id: str,
    ) -> tuple[list[dict[str, Any]], int]:
        stmt = select(MaReportModel)
        if symbol:
            stmt = stmt.where(MaReportModel.symbol == symbol)
        if trade_date:
            stmt = stmt.where(MaReportModel.trade_date == trade_date)
        stmt = stmt.order_by(MaReportModel.created_at.desc(), MaReportModel.id.desc())
        rows, total = await self._page(stmt, page, size)
        return [_report(r) for r in rows], total

    async def report_detail(
        self, report_id: int, request_id: str
    ) -> dict[str, Any] | None:
        async with self._sf() as session:
            r = await session.get(MaReportModel, report_id)
            if r is None:
                return None
            sections = (
                (
                    await session.execute(
                        select(MaReportSectionModel)
                        .where(MaReportSectionModel.report_id == report_id)
                        .order_by(MaReportSectionModel.id)
                    )
                )
                .scalars()
                .all()
            )
            evidence = (
                (
                    await session.execute(
                        select(MaEvidenceModel)
                        .where(MaEvidenceModel.report_id == report_id)
                        .order_by(MaEvidenceModel.id)
                    )
                )
                .scalars()
                .all()
            )
            decisions = (
                (
                    await session.execute(
                        select(MaDecisionModel)
                        .where(MaDecisionModel.report_id == report_id)
                        .order_by(MaDecisionModel.id)
                    )
                )
                .scalars()
                .all()
            )
        return {
            **_report(r),
            "header_facts": r.header_facts,
            "strategy": r.strategy,
            "sections": [
                {
                    "role": s.role,
                    "status": s.status,
                    "content": s.content,
                    "run_id": s.run_id,
                    "tokens": int(s.tokens or 0),
                    "cost_usd": _num(s.cost_usd),
                }
                for s in sections
            ],
            "evidence": [
                {
                    "source": e.source,
                    "tool": e.tool,
                    "args": e.args,
                    "payload": (e.payload or "")[:EVIDENCE_MAX] or None,
                    "is_error": bool(e.is_error),
                    "fetched_at": _iso(e.fetched_at),
                }
                for e in evidence
            ],
            "decisions": [_decision(d) for d in decisions],
        }

    async def list_rounds(
        self, *, page: int, size: int, request_id: str
    ) -> tuple[list[dict[str, Any]], int]:
        stmt = select(MaRoundModel).order_by(
            MaRoundModel.started_at.desc(), MaRoundModel.id.desc()
        )
        rows, total = await self._page(stmt, page, size)
        return [_round(r) for r in rows], total

    async def round_detail(
        self, round_id: int, request_id: str
    ) -> dict[str, Any] | None:
        async with self._sf() as session:
            r = await session.get(MaRoundModel, round_id)
            if r is None:
                return None
            items = (
                (
                    await session.execute(
                        select(MaRoundItemModel)
                        .where(MaRoundItemModel.round_id == round_id)
                        .order_by(MaRoundItemModel.id)
                    )
                )
                .scalars()
                .all()
            )
        return {
            **_round(r),
            "items": [
                {
                    "id": int(i.id),
                    "symbol": i.symbol,
                    "name": i.name,
                    "signals": i.signals or [],
                    "status": i.status,
                    "error": i.error,
                    "report_id": i.report_id,
                    "tokens": int(i.tokens or 0),
                    "cost_usd": _num(i.cost_usd),
                }
                for i in items
            ],
        }

    # ── 인사이트 ──────────────────────────────────────────────────────────

    async def principles(self, request_id: str) -> list[dict[str, Any]]:
        async with self._sf() as session:
            rows = (await session.execute(select(MaPrincipleModel))).scalars().all()
        rows = sorted(
            rows,
            key=lambda p: (
                not p.is_active,
                PRIORITY_RANK.get(p.priority, 9),
                -int(p.confidence),
                -int(p.supporting_count or 1),
                p.id,
            ),
        )
        return [
            {
                "id": int(p.id),
                "condition": p.condition_text,
                "action": p.action_text,
                "reason": p.reason,
                "scope": p.scope,
                "priority": p.priority,
                "confidence": int(p.confidence),
                "supporting_count": int(p.supporting_count or 1),
                "is_active": bool(p.is_active),
                "source_journal_id": p.source_journal_id,
                "updated_by": p.updated_by,
                "updated_at": _iso(p.updated_at),
            }
            for p in rows
        ]

    async def recent_journals(
        self, limit: int, request_id: str
    ) -> list[dict[str, Any]]:
        stmt = (
            select(MaJournalModel, MaPositionModel)
            .join(MaPositionModel, MaPositionModel.id == MaJournalModel.position_id)
            .order_by(MaJournalModel.created_at.desc(), MaJournalModel.id.desc())
            .limit(limit)
        )
        async with self._sf() as session:
            rows = (await session.execute(stmt)).all()
        return [
            {
                **_journal(j),
                "symbol": p.symbol,
                "name": p.name,
                "profit_rate": _num(p.profit_rate),
                "exit_reason": p.exit_reason,
            }
            for j, p in rows
        ]
