"""저널 · 원칙 저장소 (module-7).

Design Ref: stock-analysis-agents §3.3, §6 PrincipleSelectionPolicy, DD9.
application.ports 의 JournalStore ·
PrincipleStore · PrincipleReader 를 구조적 타이핑으로
맞춘다. 저널은 position_id UNIQUE 위반을 잡아 None 을 돌려준다(같은 청산을 두 번 쓰지
않게). 원칙 후보는 조건·행동·scope 가 같은(공백·대소문자 무시) 기존 원칙이 있으면
근거 거래 수를 올리고 확신도는 큰 쪽으로 둔다 — 활성 여부는 바꾸지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.market_analysis.account import ActivePrinciple
from src.domain.market_analysis.principle import (
    ClosedPosition,
    DecisionSummary,
    JournalDraft,
    PrincipleCandidate,
    PrincipleMergePolicy,
    PrincipleRecord,
    PrincipleSelectionPolicy,
    principle_key,
)
from src.infrastructure.market_analysis.models import (
    MaDecisionModel,
    MaJournalModel,
    MaPositionModel,
    MaPrincipleModel,
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _dec(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


class JournalRepository:
    def __init__(
        self, session_factory: Callable[[], Any], logger: LoggerInterface
    ) -> None:
        self._sf = session_factory
        self._logger = logger

    async def closed_position(
        self, position_id: int, request_id: str
    ) -> ClosedPosition | None:
        async with self._sf() as session:
            p = await session.get(MaPositionModel, position_id)
        if p is None or p.status != "closed" or p.exit_price is None:
            return None
        return ClosedPosition(
            id=int(p.id),
            symbol=p.symbol,
            name=p.name,
            sector=p.sector,
            entry_price=Decimal(str(p.entry_price)),
            entry_at=p.entry_at,
            exit_price=Decimal(str(p.exit_price)),
            exit_at=p.exit_at or p.updated_at,
            exit_reason=p.exit_reason or "",
            profit_rate=Decimal(str(p.profit_rate or 0)),
            holding_days=int(p.holding_days or 0),
            target_price=Decimal(str(p.target_price)),
            stop_loss=Decimal(str(p.stop_loss)),
        )

    async def decisions_for(
        self, position_id: int, request_id: str
    ) -> list[DecisionSummary]:
        stmt = (
            select(MaDecisionModel)
            .where(MaDecisionModel.position_id == position_id)
            .order_by(MaDecisionModel.created_at, MaDecisionModel.id)
        )
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [
            DecisionSummary(
                kind=d.kind,
                decision=d.decision,
                score=d.score,
                confidence=d.confidence,
                price_at_decision=_dec(d.price_at_decision),
                target_price=_dec(d.target_price),
                stop_loss=_dec(d.stop_loss),
                rationale=d.rationale,
                skip_reason=d.skip_reason,
                created_at=d.created_at,
            )
            for d in rows
        ]

    async def has_journal(self, position_id: int, request_id: str) -> bool:
        async with self._sf() as session:
            row = await session.execute(
                select(MaJournalModel.id).where(
                    MaJournalModel.position_id == position_id
                )
            )
            return row.first() is not None

    async def save_journal(self, draft: JournalDraft, request_id: str) -> int | None:
        row = MaJournalModel(
            position_id=draft.position_id,
            one_line=draft.one_line,
            situation=draft.situation,
            evaluation=draft.evaluation,
            lessons=list(draft.lessons) or None,
            tags=list(draft.tags) or None,
            raw_answer=draft.raw_answer,
            run_id=draft.run_id,
            created_at=draft.created_at,
        )
        try:
            async with self._sf() as session, session.begin():
                session.add(row)
                await session.flush()
                return int(row.id)
        except IntegrityError:
            return None


class PrincipleRepository:
    def __init__(
        self, session_factory: Callable[[], Any], logger: LoggerInterface
    ) -> None:
        self._sf = session_factory
        self._logger = logger

    async def active(
        self, *, scope: str, limit: int, request_id: str
    ) -> list[ActivePrinciple]:
        """application.ports.PrincipleReader — 판단 입력에 넣을 활성 원칙 (SC-5)."""
        stmt = select(MaPrincipleModel).where(MaPrincipleModel.is_active.is_(True))
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
        picked = PrincipleSelectionPolicy.select(
            [_record(r) for r in rows], scope=scope, limit=limit
        )
        return [ActivePrinciple(id=p.id, text=p.text) for p in picked]

    async def add_candidates(
        self,
        *,
        journal_id: int,
        candidates: list[PrincipleCandidate],
        auto_activate: bool,
        request_id: str,
    ) -> list[int]:
        ids: list[int] = []
        now = _now()
        async with self._sf() as session, session.begin():
            existing = (await session.execute(select(MaPrincipleModel))).scalars().all()
            by_key = {
                principle_key(r.condition_text, r.action_text, r.scope): r
                for r in existing
            }
            for c in candidates:
                key = principle_key(c.condition, c.action, c.scope)
                row = by_key.get(key)
                if row is not None:
                    row.supporting_count = int(row.supporting_count or 1) + 1
                    row.confidence = PrincipleMergePolicy.merged_confidence(
                        int(row.confidence), c.confidence
                    )
                    row.updated_at = now
                else:
                    row = MaPrincipleModel(
                        condition_text=c.condition[:500],
                        action_text=c.action[:500],
                        reason=c.reason,
                        scope=c.scope,
                        priority=c.priority,
                        confidence=c.confidence,
                        supporting_count=1,
                        is_active=auto_activate,
                        source_journal_id=journal_id,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(row)
                    by_key[key] = row
                await session.flush()
                ids.append(int(row.id))
        return ids

    async def set_active(
        self,
        *,
        principle_id: int,
        is_active: bool,
        priority: str | None,
        updated_by: str,
        request_id: str,
    ) -> bool:
        async with self._sf() as session, session.begin():
            row = await session.get(MaPrincipleModel, principle_id)
            if row is None:
                return False
            row.is_active = is_active
            if priority is not None:
                row.priority = priority
            row.updated_by = updated_by[:100]
            row.updated_at = _now()
            return True


def _record(r: MaPrincipleModel) -> PrincipleRecord:
    return PrincipleRecord(
        id=int(r.id),
        condition_text=r.condition_text,
        action_text=r.action_text,
        scope=r.scope,
        priority=r.priority,
        confidence=int(r.confidence),
        supporting_count=int(r.supporting_count or 1),
        is_active=bool(r.is_active),
        created_at=r.created_at,
    )
