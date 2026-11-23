"""document-revision 애플리케이션 입출력 (Design §4.2 #2)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class RevisionUploadOptions:
    """업로드 요청의 개정 관련 선택 입력."""

    supersedes_document_id: str | None = None
    version_label: str | None = None
    effective_date: date | None = None
    revision_check_id: str | None = None


@dataclass(frozen=True)
class RevisionApplyResult:
    """업로드 응답의 revision 블록. applied=False 이고 reason=None 이면 개정 요청 없음."""

    applied: bool
    lineage_id: str | None
    version_no: int
    superseded_document_id: str | None
    sync_state: str | None
    reason: str | None = None


@dataclass(frozen=True)
class KbUploadOutcome:
    result: Any  # UnifiedUploadResult
    kb: Any  # KnowledgeBase
    summary_launch: Any  # SectionSummaryLaunchInfo | None
    revision: RevisionApplyResult
