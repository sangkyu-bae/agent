from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional


@dataclass(frozen=True)
class DocumentSummary:
    document_id: str
    filename: str
    category: str
    chunk_count: int
    chunk_types: List[str]
    user_id: str


@dataclass(frozen=True)
class ChunkDetail:
    chunk_id: str
    chunk_index: int
    chunk_type: str
    content: str
    metadata: Dict[str, str]


@dataclass(frozen=True)
class ParentChunkGroup:
    chunk_id: str
    chunk_index: int
    chunk_type: str
    content: str
    children: List[ChunkDetail]


@dataclass(frozen=True)
class DocumentMetadata:
    document_id: str
    collection_name: str
    filename: str
    category: str
    user_id: str
    chunk_count: int
    chunk_strategy: str
    # kb-management-ui D2: 논리 KB 지정 업로드만 값 보유. None = 일반 업로드.
    kb_id: Optional[str] = None
    # document-revision Design §3.3: 적재 시점의 계보 필드(신규 행에만 저장).
    #   개정 상태(revision_status·sync_state)는 개정 전용 리포지토리가 소유한다.
    file_hash: Optional[str] = None
    lineage_id: Optional[str] = None
    version_no: int = 1
    version_label: Optional[str] = None
    effective_date: Optional[date] = None


@dataclass(frozen=True)
class KbDocumentSummary:
    """지식베이스 문서 목록 항목 (kb-management-ui D1)."""

    document_id: str
    filename: str
    chunk_count: int
    chunk_strategy: str
    created_at: Optional[datetime]
    # kb-document-management FR-08: 문서별 삭제 가능 여부 계산용 업로더
    user_id: str = ""
    # document-revision §4.2 #3: 버전 표시
    version_no: int = 1
    version_label: Optional[str] = None
    effective_date: Optional[date] = None
    revision_status: str = "active"
    sync_state: str = "synced"
    lineage_id: Optional[str] = None


@dataclass(frozen=True)
class DocumentChunksResult:
    document_id: str
    filename: str
    chunk_strategy: str
    total_chunks: int
    chunks: List[ChunkDetail] = field(default_factory=list)
    parents: Optional[List[ParentChunkGroup]] = None


@dataclass(frozen=True)
class DeleteDocumentResult:
    document_id: str
    collection_name: str
    filename: str
    deleted_qdrant_chunks: int
    deleted_es_chunks: int
    status: str
    error: Optional[str] = None
    # document-revision §4.2 #9: 최신 버전 삭제 시 다시 검색에 쓰이게 된 이전 버전
    restored_document_id: Optional[str] = None
