"""Domain entities for vector storage.

These are the core domain objects representing documents and vectors.
No external API calls (LLM, Qdrant, etc.) are allowed in domain layer.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional

from src.domain.vector.value_objects import DocumentId


@dataclass(frozen=True)
class Document:
    """Represents a document with its embedding vector.

    A document contains:
    - id: Optional identifier (None before persistence)
    - content: The text content of the document
    - vector: The embedding vector representation
    - metadata: Key-value pairs for filtering (document_type, parent_id, etc.)
    - score: Optional similarity score (set when returned from search)
    """

    id: Optional[DocumentId]
    content: str
    vector: List[float]
    metadata: Dict[str, str]
    score: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.content or not self.content.strip():
            raise ValueError("Document content cannot be empty")
        if not self.vector:
            raise ValueError("Document vector cannot be empty")
        if self.score is not None and (self.score < 0 or self.score > 1):
            raise ValueError("Score must be between 0 and 1")

    @property
    def vector_dimension(self) -> int:
        """Return the dimension of the embedding vector."""
        return len(self.vector)

    def has_score(self) -> bool:
        """Check if this document has a similarity score set."""
        return self.score is not None
