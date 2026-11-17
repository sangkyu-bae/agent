"""SessionScopedDecisionStore — 엔티티 판정 기록·검토 큐 (V089).

Design Ref: graph-rag-foundation §3.3·§3.4 — 앱 수명 싱글턴, 호출마다 짧은 세션.
같은 decision_id(uuid5)는 덮어쓴다. 단, 이미 검토된 행(approved·rejected)은
재추출이 다시 검토 대기로 되돌리지 않도록 검토 필드와 연결 엔티티를 유지한다.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, update

from src.domain.graph_rag.interfaces import DecisionStorePort
from src.domain.graph_rag.resolution import (
    DecidedBy,
    LlmConfidence,
    ResolutionBand,
    ResolutionDecision,
    ReviewStatus,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.graph_rag.models import GraphResolutionDecisionModel as Row

_REVIEWED = (ReviewStatus.APPROVED.value, ReviewStatus.REJECTED.value)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _to_domain(r: Row) -> ResolutionDecision:
    return ResolutionDecision(
        id=r.id,
        job_id=r.job_id,
        document_id=r.document_id,
        chunk_id=r.chunk_id,
        mention_text=r.mention_text,
        mention_type=r.mention_type,
        candidates=tuple(r.candidates or ()),
        probabilities=r.probabilities,
        chosen_label=r.chosen_label,
        entity_id=r.entity_id,
        created_new=bool(r.created_new),
        decided_by=DecidedBy(r.decided_by),
        band=ResolutionBand(r.band),
        probability=float(r.probability) if r.probability is not None else None,
        llm_confidence=LlmConfidence(r.llm_confidence) if r.llm_confidence else None,
        llm_reason=r.llm_reason,
        review_status=ReviewStatus(r.review_status),
        reviewed_by=r.reviewed_by,
        reviewed_at=r.reviewed_at,
        review_note=r.review_note,
        created_at=r.created_at,
    )


def _apply(row: Row, d: ResolutionDecision) -> None:
    row.job_id, row.document_id, row.chunk_id = d.job_id, d.document_id, d.chunk_id
    row.mention_text, row.mention_type = d.mention_text[:255], d.mention_type
    row.candidates, row.probabilities = list(d.candidates), d.probabilities
    row.chosen_label, row.created_new = d.chosen_label, d.created_new
    row.decided_by, row.band = d.decided_by.value, d.band.value
    row.probability = (
        Decimal(str(round(d.probability, 4))) if d.probability is not None else None
    )
    row.llm_confidence = d.llm_confidence.value if d.llm_confidence else None
    row.llm_reason = d.llm_reason
    if row.review_status not in _REVIEWED:  # 검토된 판정은 결과를 유지
        row.entity_id = d.entity_id
        row.review_status = d.review_status.value


class SessionScopedDecisionStore(DecisionStorePort):
    def __init__(self, session_factory: Callable[[], Any], logger: LoggerInterface):
        self._session_factory = session_factory
        self._logger = logger

    async def upsert_many(
        self, decisions: list[ResolutionDecision], request_id: str
    ) -> None:
        if not decisions:
            return
        async with self._session_factory() as session, session.begin():
            for d in decisions:
                row = await session.get(Row, d.id)
                if row is None:
                    row = Row(
                        id=d.id,
                        review_status=ReviewStatus.NONE.value,
                        created_at=_now(),
                    )
                    session.add(row)
                _apply(row, d)

    async def get(self, decision_id: str, request_id: str) -> ResolutionDecision | None:
        async with self._session_factory() as session:
            row = await session.get(Row, decision_id)
            return _to_domain(row) if row else None

    async def list_by_review_status(
        self, status: ReviewStatus, limit: int, offset: int, request_id: str
    ) -> tuple[list[ResolutionDecision], int]:
        where = Row.review_status == status.value
        async with self._session_factory() as session:
            total = (
                await session.execute(
                    select(func.count()).select_from(Row).where(where)
                )
            ).scalar_one()
            rows = (
                (
                    await session.execute(
                        select(Row)
                        .where(where)
                        .order_by(Row.created_at.desc(), Row.id)
                        .limit(limit)
                        .offset(offset)
                    )
                )
                .scalars()
                .all()
            )
        return [_to_domain(r) for r in rows], int(total)

    async def mark_reviewed(
        self,
        decision_id: str,
        status: ReviewStatus,
        reviewer: str,
        note: str | None,
        entity_id: str,
        request_id: str,
    ) -> None:
        async with self._session_factory() as session, session.begin():
            await session.execute(
                update(Row)
                .where(Row.id == decision_id)
                .values(
                    review_status=status.value,
                    reviewed_by=reviewer,
                    reviewed_at=_now(),
                    review_note=(note or None) and note[:500],
                    entity_id=entity_id,
                )
            )
        self._logger.info(
            "graph decision reviewed",
            request_id=request_id,
            decision_id=decision_id,
            status=status.value,
        )
