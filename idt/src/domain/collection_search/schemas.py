from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CollectionSearchRequest:
    collection_name: str
    query: str
    top_k: int = 10
    bm25_top_k: int = 20
    vector_top_k: int = 20
    rrf_k: int = 60
    bm25_weight: float = 0.5
    vector_weight: float = 0.5
    document_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.collection_name or not self.collection_name.strip():
            raise ValueError("collection_name cannot be empty")
        if not self.query or not self.query.strip():
            raise ValueError("query cannot be empty")
        if not (0.0 <= self.bm25_weight <= 1.0):
            raise ValueError("bm25_weight must be between 0.0 and 1.0")
        if not (0.0 <= self.vector_weight <= 1.0):
            raise ValueError("vector_weight must be between 0.0 and 1.0")


@dataclass(frozen=True)
class CollectionSearchResponse:
    query: str
    collection_name: str
    results: list
    total_found: int
    bm25_weight: float
    vector_weight: float
    request_id: str
    document_id: Optional[str] = None
