"""MorphIndex application-layer schemas."""
from dataclasses import dataclass, field


@dataclass
class MorphIndexRequest:
    """Kiwi 형태소 분석 + Qdrant + ES 이중 색인 요청."""

    document_id: str
    content: str
    user_id: str
    strategy_type: str = "parent_child"
    chunk_size: int = 500
    chunk_overlap: int = 50
    source: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class DualIndexedChunk:
    """Qdrant + ES에 동시 색인된 단일 청크 정보."""

    chunk_id: str
    chunk_type: str
    morph_keywords: list[str]
    content: str
    char_start: int
    char_end: int
    chunk_index: int


@dataclass
class MorphIndexResult:
    """Kiwi 형태소 + 이중 색인 결과."""

    document_id: str
    user_id: str
    total_chunks: int
    qdrant_indexed: int
    es_indexed: int
    indexed_chunks: list[DualIndexedChunk]
    request_id: str
