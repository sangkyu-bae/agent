from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class SearchHistoryEntry:
    id: int
    user_id: str
    collection_name: str
    query: str
    bm25_weight: float
    vector_weight: float
    top_k: int
    result_count: int
    created_at: datetime
    document_id: Optional[str] = None
    kb_id: Optional[str] = None


@dataclass(frozen=True)
class SearchHistoryListResult:
    collection_name: str
    histories: list[SearchHistoryEntry]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class KbSearchHistoryListResult:
    """KB 단위 히스토리 조회 결과 (kb-retrieval-test D8)."""

    kb_id: str
    histories: list[SearchHistoryEntry]
    total: int
    limit: int
    offset: int
