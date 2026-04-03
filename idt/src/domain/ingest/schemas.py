"""Domain schemas for PDF ingest pipeline.

Pure data objects — no external dependencies, no LangChain imports.
"""
from typing import List
from pydantic import BaseModel, field_validator


class IngestRequest(BaseModel):
    """Request to ingest a PDF: parse + chunk + embed + store.

    Attributes:
        filename: Original PDF filename
        user_id: Owner of the document
        request_id: Trace ID for LOG-001
        file_bytes: Raw PDF bytes
        parser_type: "pymupdf" | "llamaparser" (default: "pymupdf")
        chunking_strategy: "full_token" | "parent_child" | "semantic" (default: "full_token")
        chunk_size: Token size per chunk
        chunk_overlap: Overlap between chunks
    """

    filename: str
    user_id: str
    request_id: str
    file_bytes: bytes
    parser_type: str = "pymupdf"
    chunking_strategy: str = "full_token"
    chunk_size: int = 1000
    chunk_overlap: int = 100

    @field_validator("filename")
    @classmethod
    def filename_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("filename cannot be empty")
        return v

    @field_validator("user_id")
    @classmethod
    def user_id_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("user_id cannot be empty")
        return v

    model_config = {"arbitrary_types_allowed": True}


class IngestResult(BaseModel):
    """Result of a PDF ingest operation.

    Attributes:
        document_id: Generated document identifier
        filename: Original filename
        user_id: Owner of the document
        total_pages: Number of parsed pages
        chunk_count: Number of chunks after splitting
        parser_used: Name of parser that was used
        chunking_strategy: Name of chunking strategy used
        stored_ids: IDs of vectors stored in vector DB
        request_id: Trace ID for LOG-001
    """

    document_id: str
    filename: str
    user_id: str
    total_pages: int
    chunk_count: int
    parser_used: str
    chunking_strategy: str
    stored_ids: List[str]
    request_id: str
