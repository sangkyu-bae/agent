from dataclasses import dataclass, field
from datetime import datetime
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


@dataclass(frozen=True)
class KbDocumentSummary:
    """지식베이스 문서 목록 항목 (kb-management-ui D1)."""

    document_id: str
    filename: str
    chunk_count: int
    chunk_strategy: str
    created_at: Optional[datetime]


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
