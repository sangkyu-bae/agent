"""Pydantic schemas for chunking request/response DTOs."""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, field_validator


VALID_STRATEGY_TYPES = {"full_token", "parent_child", "semantic"}


class ChunkRequest(BaseModel):
    """Request schema for document chunking.

    Attributes:
        document_id: Unique identifier of the document.
        content: Document content to chunk.
        strategy_type: Chunking strategy to use.
        metadata: Optional metadata to include in chunks.
        chunk_size: Optional custom chunk size.
        chunk_overlap: Optional custom chunk overlap.
    """
    document_id: str
    content: str
    strategy_type: str
    metadata: Optional[Dict[str, Any]] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None

    @field_validator("strategy_type")
    @classmethod
    def validate_strategy_type(cls, v: str) -> str:
        if v not in VALID_STRATEGY_TYPES:
            raise ValueError(
                f"strategy_type must be one of: {', '.join(sorted(VALID_STRATEGY_TYPES))}"
            )
        return v


class ChunkResult(BaseModel):
    """Schema for a single chunk result.

    Attributes:
        chunk_id: Unique identifier of the chunk.
        content: Chunk text content.
        chunk_type: Type of chunk (full, parent, child, semantic).
        chunk_index: Index of this chunk.
        total_chunks: Total number of chunks.
        parent_id: Parent chunk ID (for child chunks).
        children_ids: Child chunk IDs (for parent chunks).
        metadata: Additional metadata.
    """
    chunk_id: str
    content: str
    chunk_type: Literal["full", "parent", "child", "semantic"]
    chunk_index: int
    total_chunks: int
    parent_id: Optional[str] = None
    children_ids: Optional[List[str]] = None
    metadata: Dict[str, Any]


class ChunkResponse(BaseModel):
    """Response schema for document chunking.

    Attributes:
        document_id: Document identifier.
        strategy_type: Strategy used for chunking.
        chunks: List of chunk results.
        total_chunks: Total number of chunks created.
    """
    document_id: str
    strategy_type: str
    chunks: List[ChunkResult]
    total_chunks: int
