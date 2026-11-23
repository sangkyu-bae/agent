"""document-revision 값 객체.

Design Ref: document-revision §3.1 — 버전·상태의 원본은 MySQL document_metadata,
청크 payload 의 revision_status 는 검색 제외용 사본이다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


class RevisionStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class SyncState(str, Enum):
    """청크 payload 표식이 MySQL 상태를 따라잡았는지."""

    SYNCED = "synced"
    PENDING = "pending"


class CheckVerdict(str, Enum):
    NEW = "new"
    REVISION_CANDIDATE = "revision_candidate"
    DUPLICATE = "duplicate"


class LlmVerdict(str, Enum):
    SAME = "same_document_revision"
    DIFFERENT = "different_document"
    UNCERTAIN = "uncertain"


class LlmStatus(str, Enum):
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"


class RollbackMode(str, Enum):
    DETACH = "detach"
    DELETE = "delete"


class RevisionMode(str, Enum):
    """KB 별 개정 판정 모드. AUTO 는 판정 로그 실측 후 별도 사이클 (Plan FR-15)."""

    SUGGEST = "suggest"
    AUTO = "auto"


class CheckSource(str, Enum):
    PRECHECK = "precheck"
    MANUAL_LINK = "manual_link"
    ROLLBACK = "rollback"


class CheckDecision(str, Enum):
    REVISION = "revision"
    NEW = "new"
    CANCEL = "cancel"
    ROLLBACK_DETACH = "rollback_detach"
    ROLLBACK_DELETE = "rollback_delete"


@dataclass(frozen=True)
class DocumentVersion:
    document_id: str
    kb_id: str | None
    filename: str
    lineage_id: str | None  # NULL 컬럼 = 자기 document_id 가 계보 ID
    version_no: int
    version_label: str | None
    effective_date: date | None
    revision_status: RevisionStatus
    sync_state: SyncState
    file_hash: str | None
    superseded_by: str | None
    superseded_at: datetime | None
    revised_by: str | None
    created_at: datetime | None

    @property
    def effective_lineage_id(self) -> str:
        return self.lineage_id or self.document_id

    @property
    def is_active(self) -> bool:
        return self.revision_status is RevisionStatus.ACTIVE


@dataclass(frozen=True)
class RevisionCandidate:
    document_id: str
    filename: str
    version_no: int
    version_label: str | None
    filename_score: float
    content_score: float
    combined_score: float
    llm_verdict: LlmVerdict | None
    llm_reason: str | None


@dataclass(frozen=True)
class RevisionCheckResult:
    check_id: str
    verdict: CheckVerdict
    duplicate_of: DocumentVersion | None
    candidates: list[RevisionCandidate]
    suggested_document_id: str | None
    llm_status: LlmStatus
    elapsed_ms: int


@dataclass(frozen=True)
class RevisionScoringConfig:
    """후보 선정·판정 임계값 (Design §10.4). 운영값은 Settings 에서 주입한다."""

    head_chars: int = 2000
    top_n: int = 3
    llm_top_m: int = 2
    filename_min: float = 0.6
    # Act-1 C1: 합성 평가(개정 0.65~0.70 / 무관 0.31~0.35) 중간값
    content_min: float = 0.5
    weight_filename: float = 0.4
    weight_content: float = 0.6
    suggest_min_combined: float = 0.80
    llm_timeout_s: float = 8.0


@dataclass(frozen=True)
class JudgeOutcome:
    verdict: LlmVerdict
    reason: str
    confidence: float


@dataclass(frozen=True)
class ChunkMarkResult:
    """청크 payload 표식 결과 — 둘 다 True 일 때만 sync_state=synced."""

    qdrant_ok: bool
    es_ok: bool

    @property
    def ok(self) -> bool:
        return self.qdrant_ok and self.es_ok


@dataclass(frozen=True)
class RevisionCheckLogEntry:
    """판정 로그 1행 (Design §3.3 V097, Plan FR-16)."""

    check_id: str
    kb_id: str
    user_id: str
    source: CheckSource
    filename: str
    normalized_name: str | None
    file_hash: str | None
    verdict: str  # CheckVerdict 값 또는 "manual"
    suggested_document_id: str | None
    candidates: list[RevisionCandidate]
    llm_status: LlmStatus
    elapsed_ms: int
    parse_ms: int
    decision: CheckDecision | None = None
    target_document_id: str | None = None
    decided_document_id: str | None = None
    decided_by: str | None = None
