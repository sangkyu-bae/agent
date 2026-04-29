from dataclasses import dataclass


@dataclass(frozen=True)
class UnifiedUploadRequest:
    file_bytes: bytes
    filename: str
    user_id: str
    collection_name: str
    child_chunk_size: int = 500
    child_chunk_overlap: int = 50


@dataclass
class QdrantStoreResult:
    stored_ids: list[str]
    embedding_model: str
    error: str | None = None


@dataclass
class EsStoreResult:
    indexed_count: int
    error: str | None = None


@dataclass
class UnifiedUploadResult:
    document_id: str
    filename: str
    total_pages: int
    chunk_count: int
    collection_name: str
    qdrant: QdrantStoreResult
    es: EsStoreResult
    chunking_config: dict
    status: str  # "completed" | "partial" | "failed"
