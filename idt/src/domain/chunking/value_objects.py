"""Value objects for document chunking domain."""
from dataclasses import dataclass, field
from typing import List, Optional


VALID_CHUNK_TYPES = {"parent", "child", "full", "semantic"}


@dataclass(frozen=True)
class ChunkingConfig:
    """Configuration for chunking strategy.

    Attributes:
        chunk_size: Maximum number of tokens per chunk.
        chunk_overlap: Number of overlapping tokens between chunks.
        encoding_model: Tiktoken encoding model name.
    """
    chunk_size: int
    chunk_overlap: int
    encoding_model: str = "cl100k_base"

    def __post_init__(self):
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")


@dataclass(frozen=True)
class ChunkMetadata:
    """Metadata for a document chunk.

    Attributes:
        chunk_type: Type of chunk (parent, child, full, semantic).
        chunk_index: Index of this chunk within the document.
        total_chunks: Total number of chunks from the source document.
        parent_id: ID of parent chunk (required for child chunks).
        children_ids: List of child chunk IDs (for parent chunks).
    """
    chunk_type: str
    chunk_index: int
    total_chunks: int
    parent_id: Optional[str] = None
    children_ids: Optional[List[str]] = None

    def __post_init__(self):
        if self.chunk_type not in VALID_CHUNK_TYPES:
            raise ValueError(
                f"chunk_type must be one of: {', '.join(sorted(VALID_CHUNK_TYPES))}"
            )
        if self.chunk_type == "child" and self.parent_id is None:
            raise ValueError("parent_id is required for child chunks")

    def is_parent(self) -> bool:
        """Check if this is a parent chunk."""
        return self.chunk_type == "parent"

    def is_child(self) -> bool:
        """Check if this is a child chunk."""
        return self.chunk_type == "child"

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "chunk_type": self.chunk_type,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "parent_id": self.parent_id,
            "children_ids": self.children_ids,
        }
