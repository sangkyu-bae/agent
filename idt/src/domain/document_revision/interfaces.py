"""document-revision 포트 (Design §9.4). 구현은 infrastructure/document_revision/."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime

from src.domain.document_revision.value_objects import (
    CheckDecision,
    ChunkMarkResult,
    DocumentVersion,
    JudgeOutcome,
    RevisionCheckLogEntry,
    RevisionStatus,
    SyncState,
)


class DocumentRevisionRepositoryPort(ABC):
    """document_metadata 의 개정 컬럼 조회·전환. 상태 전환은 이 포트만 수행한다."""

    @abstractmethod
    async def find_version(
        self, document_id: str, request_id: str
    ) -> DocumentVersion | None: ...

    @abstractmethod
    async def find_lineage_versions(
        self, lineage_id: str, request_id: str
    ) -> list[DocumentVersion]:
        """lineage_id 컬럼 일치 + document_id == lineage_id (계보 시작 문서) 전부."""

    @abstractmethod
    async def find_active_by_kb(
        self, kb_id: str, request_id: str
    ) -> list[DocumentVersion]: ...

    @abstractmethod
    async def find_by_hash(
        self, kb_id: str, file_hash: str, request_id: str
    ) -> list[DocumentVersion]: ...

    @abstractmethod
    async def find_pending_sync(
        self, kb_id: str, request_id: str
    ) -> list[DocumentVersion]: ...

    @abstractmethod
    async def assign_lineage(
        self,
        document_id: str,
        *,
        lineage_id: str | None,
        version_no: int,
        request_id: str,
    ) -> None:
        """계보 편입(연결) 또는 분리(lineage_id=None, version_no=1)."""

    @abstractmethod
    async def set_status(
        self,
        document_id: str,
        *,
        status: RevisionStatus,
        sync_state: SyncState,
        superseded_by: str | None,
        superseded_at: datetime | None,
        revised_by: str | None,
        request_id: str,
    ) -> None: ...

    @abstractmethod
    async def set_sync_state(
        self, document_id: str, sync_state: SyncState, request_id: str
    ) -> None: ...

    @abstractmethod
    async def update_meta(
        self,
        document_id: str,
        *,
        version_label: str | None,
        effective_date: date | None,
        request_id: str,
    ) -> None: ...


class RevisionCheckLogRepositoryPort(ABC):
    @abstractmethod
    async def save(self, entry: RevisionCheckLogEntry, request_id: str) -> None: ...

    @abstractmethod
    async def record_decision(
        self,
        check_id: str,
        *,
        decision: CheckDecision,
        target_document_id: str | None,
        decided_document_id: str | None,
        decided_by: str,
        request_id: str,
    ) -> None: ...


class ChunkRevisionMarkerPort(ABC):
    """청크 payload revision_status 사본 갱신.

    Qdrant set_payload + ES update_by_query, 둘 다 멱등.
    """

    @abstractmethod
    async def mark(
        self,
        collection_name: str,
        document_id: str,
        status: RevisionStatus,
        request_id: str,
    ) -> ChunkMarkResult: ...


class RevisionJudgePort(ABC):
    """두 문서 앞부분으로 '같은 문서의 개정인지' 판정. 실패는 예외로 알린다."""

    @abstractmethod
    async def judge(
        self,
        *,
        new_filename: str,
        new_head: str,
        candidate_filename: str,
        candidate_head: str,
        request_id: str,
    ) -> JudgeOutcome | None:
        """보조 LLM 미설정이면 None (llm_status=skipped)."""


class HeadSimilaritySearchPort(ABC):
    @abstractmethod
    async def search(
        self,
        *,
        collection_name: str,
        kb_id: str,
        head_text: str,
        request_id: str,
    ) -> dict[str, float]:
        """같은 KB active 문서별 본문 유사도(document_id → 0.0~1.0)."""


class CandidateHeadReaderPort(ABC):
    @abstractmethod
    async def read(
        self, document_id: str, max_chars: int, request_id: str
    ) -> str: ...
