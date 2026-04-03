"""ChunkAndIndex application-layer schemas."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ChunkAndIndexRequest:
    """청킹 + ES 키워드 색인 요청."""

    document_id: str
    content: str
    user_id: str
    strategy_type: str = "parent_child"
    metadata: dict = field(default_factory=dict)
    chunk_size: int = 500
    chunk_overlap: int = 50
    top_keywords: int = 10


@dataclass
class IndexedChunk:
    """ES에 색인된 단일 청크 정보."""

    chunk_id: str
    chunk_type: str
    keywords: list[str]
    content: str


@dataclass
class ChunkAndIndexResult:
    """청킹 + ES 색인 결과."""

    document_id: str
    user_id: str
    total_chunks: int
    indexed_chunks: list[IndexedChunk]
    request_id: str
