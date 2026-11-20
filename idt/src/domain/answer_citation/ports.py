"""답변 인용 저장 포트 (answer-citation-verification §3.3, D-11)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.domain.answer_citation.models import (
    AnswerCitation,
    CitationOutcome,
    CitationStatus,
    NoneReason,
)


@dataclass(frozen=True)
class StoredRunCitations:
    run_id: str
    status: CitationStatus
    citations: tuple[AnswerCitation, ...]
    none_reason: NoneReason | None = None


class AnswerCitationRepositoryPort(ABC):
    @abstractmethod
    async def save(
        self,
        run_id: str,
        outcome: CitationOutcome,
        *,
        judge_model: str | None,
        request_id: str,
    ) -> None:
        """실행당 1행. commit 은 세션 소유자 몫."""

    @abstractmethod
    async def find_by_runs(
        self, run_ids: list[str], request_id: str
    ) -> dict[str, StoredRunCitations]:
        """행이 없는 실행은 키가 없다(= not_applicable, Design D-12)."""
