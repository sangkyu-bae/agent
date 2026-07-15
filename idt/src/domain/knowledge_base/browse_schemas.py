"""KB 저장 내용 조회 결과 스키마 — kb-content-browser Design §4.2.

두 저장소(Qdrant/ES) 결과를 동일 형태로 정규화한 값 객체 (D5).
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.domain.doc_browse.schemas import ChunkDetail, ParentChunkGroup


@dataclass(frozen=True)
class KbDocumentSummaryResult:
    """문서 요약 조회 결과. 미생성 시 exists=False (D6)."""

    exists: bool
    source: str
    chunk_id: Optional[str] = None
    summary_text: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    section_count: Optional[int] = None
    filename: Optional[str] = None
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class KbSectionSummaryItem:
    chunk_id: str
    section_ref: str
    clause_title: str
    chunk_index: int
    summary_text: str
    keywords: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class KbSectionSummaryListResult:
    source: str
    document_id: str
    total: int
    items: List[KbSectionSummaryItem] = field(default_factory=list)


@dataclass(frozen=True)
class KbDocumentChunksResult:
    """KB 스코프 청크 조회 결과. search_mode: match(es)/contains(qdrant)/None (D3)."""

    source: str
    search_mode: Optional[str]
    document_id: str
    filename: str
    chunk_strategy: str
    total_chunks: int
    chunks: List[ChunkDetail] = field(default_factory=list)
    parents: Optional[List[ParentChunkGroup]] = None
