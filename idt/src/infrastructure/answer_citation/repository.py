"""답변 인용 저장소 (answer-citation-verification §3.3, D-11).

- AnswerCitationRepository: 요청 세션용. commit/rollback 하지 않는다(CLAUDE.md §6).
- SessionScopedAnswerCitationStore: 그래프 실행 중(답변 노드)·실시간 칩 조회처럼
  요청 세션 밖에서 쓰는 어댑터 — 호출마다 짧은 세션을 열고 저장이면 commit 한다
  (SessionScopedRunSourcesReader 선례).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.answer_citation.models import AnswerCitation, CitationOutcome
from src.domain.answer_citation.ports import (
    AnswerCitationRepositoryPort,
    StoredRunCitations,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.answer_citation.models import AnswerCitationModel

_FIELDS = ("no", "marker", "chunk_id", "document_id", "page", "evidence", "sentence")


class AnswerCitationRepository(AnswerCitationRepositoryPort):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(
        self,
        run_id: str,
        outcome: CitationOutcome,
        *,
        judge_model: str | None,
        request_id: str,
    ) -> None:
        row = await self._session.get(AnswerCitationModel, run_id)
        if row is None:
            row = AnswerCitationModel(
                run_id=run_id, created_at=datetime.now(UTC).replace(tzinfo=None)
            )
            self._session.add(row)
        row.status = outcome.status
        row.none_reason = outcome.none_reason
        row.citations = [_to_json(c) for c in outcome.citations]
        row.judge_model = judge_model
        await self._session.flush()
        self._logger.info(
            "answer citation saved",
            request_id=request_id,
            run_id=run_id,
            status=outcome.status,
            citation_count=len(outcome.citations),
        )

    async def find_by_runs(
        self, run_ids: list[str], request_id: str
    ) -> dict[str, StoredRunCitations]:
        if not run_ids:
            return {}
        stmt = select(AnswerCitationModel).where(
            AnswerCitationModel.run_id.in_(run_ids)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return {row.run_id: _to_stored(row) for row in rows}


class SessionScopedAnswerCitationStore:
    def __init__(
        self, session_factory: Callable[[], Any], logger: LoggerInterface
    ) -> None:
        self._session_factory = session_factory
        self._logger = logger

    async def save(
        self,
        run_id: str,
        outcome: CitationOutcome,
        *,
        judge_model: str | None,
        request_id: str,
    ) -> None:
        async with self._session_factory() as session:
            await AnswerCitationRepository(session, self._logger).save(
                run_id, outcome, judge_model=judge_model, request_id=request_id
            )
            await session.commit()

    async def find_by_runs(
        self, run_ids: list[str], request_id: str
    ) -> dict[str, StoredRunCitations]:
        async with self._session_factory() as session:
            return await AnswerCitationRepository(session, self._logger).find_by_runs(
                run_ids, request_id
            )


def _to_json(c: AnswerCitation) -> dict:
    return {name: getattr(c, name) for name in _FIELDS}


def _to_stored(row: AnswerCitationModel) -> StoredRunCitations:
    citations = tuple(
        AnswerCitation(**{name: item.get(name) for name in _FIELDS})
        for item in row.citations or []
    )
    return StoredRunCitations(
        run_id=row.run_id,
        status=row.status,
        citations=citations,
        none_reason=row.none_reason,
    )
