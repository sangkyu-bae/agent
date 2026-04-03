"""Domain schemas for retrieval use case.

Value objects representing retrieval requests and results.
No external API calls allowed in domain layer.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class RetrievalRequest:
    """User query and retrieval options."""

    query: str
    user_id: str
    request_id: str
    top_k: int = 10
    document_id: Optional[str] = None
    use_query_rewrite: bool = False
    use_compression: bool = True
    use_parent_context: bool = True


@dataclass(frozen=True)
class RetrievedDocument:
    """Single retrieved document with metadata."""

    id: str
    content: str
    score: float
    metadata: Dict[str, str]
    parent_content: Optional[str] = None


@dataclass(frozen=True)
class RetrievalResult:
    """Final retrieval result returned to caller."""

    query: str
    rewritten_query: Optional[str]
    documents: List[RetrievedDocument]
    total_found: int
    request_id: str
