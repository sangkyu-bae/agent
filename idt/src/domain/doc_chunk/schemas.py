"""Pydantic schemas for doc-chunk upload request/result."""
from typing import Any, Dict, List

from pydantic import BaseModel, field_validator

SUPPORTED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".txt", ".md"}
VALID_STRATEGY_TYPES = {"full_token", "parent_child", "semantic"}


class DocChunkRequest(BaseModel):
    """File upload + chunking request."""

    filename: str
    user_id: str
    request_id: str
    file_bytes: bytes
    strategy_type: str = "parent_child"
    chunk_size: int = 500
    chunk_overlap: int = 50

    @field_validator("strategy_type")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        if v not in VALID_STRATEGY_TYPES:
            raise ValueError(
                f"strategy_type must be one of: {sorted(VALID_STRATEGY_TYPES)}"
            )
        return v

    @field_validator("chunk_size")
    @classmethod
    def validate_chunk_size(cls, v: int) -> int:
        if v < 100:
            raise ValueError("chunk_size must be >= 100")
        return v


class DocChunkItem(BaseModel):
    """Single chunk result."""

    chunk_id: str
    content: str
    chunk_type: str
    chunk_index: int
    metadata: Dict[str, Any]


class DocChunkResult(BaseModel):
    """Full chunking result for an uploaded file."""

    filename: str
    user_id: str
    strategy_used: str
    total_chunks: int
    chunks: List[DocChunkItem]
    request_id: str
