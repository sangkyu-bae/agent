"""document-revision API 스키마 (Design §4.2). 프론트 타입: idt_front/src/types/knowledgeBase.ts."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from src.application.document_revision.schemas import RevisionApplyResult
from src.domain.document_revision.errors import (
    DocumentRevisionError,
    DuplicateDocumentError,
)
from src.domain.document_revision.value_objects import (
    DocumentVersion,
    RevisionCheckResult,
)


class RevisionApplyResponse(BaseModel):
    """업로드 응답 revision 블록 (§4.2 #2)."""

    applied: bool
    lineage_id: str | None
    version_no: int
    superseded_document_id: str | None
    sync_state: str | None
    reason: str | None = None

    @classmethod
    def from_result(cls, r: RevisionApplyResult) -> RevisionApplyResponse:
        return cls(
            applied=r.applied,
            lineage_id=r.lineage_id,
            version_no=r.version_no,
            superseded_document_id=r.superseded_document_id,
            sync_state=r.sync_state,
            reason=r.reason,
        )


class DocumentVersionResponse(BaseModel):
    document_id: str
    filename: str
    lineage_id: str
    version_no: int
    version_label: str | None
    effective_date: date | None
    revision_status: str
    sync_state: str
    superseded_by: str | None
    superseded_at: datetime | None
    revised_by: str | None
    created_at: datetime | None

    @classmethod
    def from_version(cls, v: DocumentVersion) -> DocumentVersionResponse:
        return cls(
            document_id=v.document_id,
            filename=v.filename,
            lineage_id=v.effective_lineage_id,
            version_no=v.version_no,
            version_label=v.version_label,
            effective_date=v.effective_date,
            revision_status=v.revision_status.value,
            sync_state=v.sync_state.value,
            superseded_by=v.superseded_by,
            superseded_at=v.superseded_at,
            revised_by=v.revised_by,
            created_at=v.created_at,
        )


class RevisionCandidateResponse(BaseModel):
    document_id: str
    filename: str
    version_no: int
    version_label: str | None
    filename_score: float
    content_score: float
    combined_score: float
    llm_verdict: str | None
    llm_reason: str | None


class RevisionCheckResponse(BaseModel):
    """사전 점검 응답 (§4.2 #1)."""

    check_id: str
    verdict: str  # new | revision_candidate | duplicate
    duplicate_of: DocumentVersionResponse | None
    suggested_document_id: str | None
    candidates: list[RevisionCandidateResponse]
    llm_status: str  # ok | failed | skipped
    elapsed_ms: int

    @classmethod
    def from_result(cls, r: RevisionCheckResult) -> RevisionCheckResponse:
        return cls(
            check_id=r.check_id,
            verdict=r.verdict.value,
            duplicate_of=(
                DocumentVersionResponse.from_version(r.duplicate_of)
                if r.duplicate_of
                else None
            ),
            suggested_document_id=r.suggested_document_id,
            candidates=[
                RevisionCandidateResponse(
                    document_id=c.document_id,
                    filename=c.filename,
                    version_no=c.version_no,
                    version_label=c.version_label,
                    filename_score=round(c.filename_score, 4),
                    content_score=round(c.content_score, 4),
                    combined_score=round(c.combined_score, 4),
                    llm_verdict=c.llm_verdict.value if c.llm_verdict else None,
                    llm_reason=c.llm_reason,
                )
                for c in r.candidates
            ],
            llm_status=r.llm_status.value,
            elapsed_ms=r.elapsed_ms,
        )


def revision_error_detail(e: DocumentRevisionError) -> dict:
    """409 detail: {code, reason, message[, document]} (§6.2)."""
    detail: dict = {"code": e.code, "reason": e.reason, "message": str(e)}
    if isinstance(e, DuplicateDocumentError):
        detail = {
            "code": e.code,
            "message": str(e),
            "document": DocumentVersionResponse.from_version(e.existing).model_dump(
                mode="json"
            ),
        }
    return detail
