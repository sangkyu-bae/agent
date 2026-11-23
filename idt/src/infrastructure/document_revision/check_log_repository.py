"""RevisionCheckLogRepository — 개정 판정 로그 (document-revision Design §3.3 V097, FR-16)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.document_revision.interfaces import RevisionCheckLogRepositoryPort
from src.domain.document_revision.value_objects import (
    CheckDecision,
    RevisionCandidate,
    RevisionCheckLogEntry,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.document_revision.models import DocumentRevisionCheckModel


def _candidate_json(c: RevisionCandidate) -> dict:
    return {
        "document_id": c.document_id,
        "filename": c.filename,
        "version_no": c.version_no,
        "version_label": c.version_label,
        "filename_score": round(c.filename_score, 4),
        "content_score": round(c.content_score, 4),
        "combined_score": round(c.combined_score, 4),
        "llm_verdict": c.llm_verdict.value if c.llm_verdict else None,
        "llm_reason": c.llm_reason,
    }


class RevisionCheckLogRepository(RevisionCheckLogRepositoryPort):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(self, entry: RevisionCheckLogEntry, request_id: str) -> None:
        self._session.add(
            DocumentRevisionCheckModel(
                id=entry.check_id,
                kb_id=entry.kb_id,
                user_id=entry.user_id,
                source=entry.source.value,
                filename=entry.filename,
                normalized_name=entry.normalized_name,
                file_hash=entry.file_hash,
                verdict=entry.verdict,
                suggested_document_id=entry.suggested_document_id,
                candidates_json=[_candidate_json(c) for c in entry.candidates],
                llm_status=entry.llm_status.value,
                elapsed_ms=entry.elapsed_ms,
                parse_ms=entry.parse_ms,
                decision=entry.decision.value if entry.decision else None,
                target_document_id=entry.target_document_id,
                decided_document_id=entry.decided_document_id,
                decided_by=entry.decided_by,
                decided_at=datetime.utcnow() if entry.decision else None,
            )
        )
        await self._session.flush()
        self._logger.info(
            "Revision check logged",
            request_id=request_id,
            check_id=entry.check_id,
            verdict=entry.verdict,
            llm_status=entry.llm_status.value,
        )

    async def record_decision(
        self,
        check_id: str,
        *,
        decision: CheckDecision,
        target_document_id: str | None,
        decided_document_id: str | None,
        decided_by: str,
        request_id: str,
    ) -> None:
        await self._session.execute(
            update(DocumentRevisionCheckModel)
            .where(DocumentRevisionCheckModel.id == check_id)
            .values(
                decision=decision.value,
                target_document_id=target_document_id,
                decided_document_id=decided_document_id,
                decided_by=decided_by,
                decided_at=datetime.utcnow(),
            )
        )
        await self._session.flush()
        self._logger.info(
            "Revision decision recorded",
            request_id=request_id,
            check_id=check_id,
            decision=decision.value,
        )
