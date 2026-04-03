"""Pydantic schema for Excel upload API response."""
from typing import List

from pydantic import BaseModel, Field


class ExcelUploadResponse(BaseModel):
    """Response schema for Excel file upload and chunking.

    Attributes:
        document_id: Unique identifier for the uploaded document.
        filename: Original filename of the uploaded Excel file.
        sheet_count: Number of sheets parsed.
        chunk_count: Total number of chunks created.
        stored_ids: List of IDs assigned by vector store.
        status: Processing status (completed / failed).
        errors: List of error messages, if any.
    """

    document_id: str
    filename: str
    sheet_count: int
    chunk_count: int
    stored_ids: List[str]
    status: str
    errors: List[str] = Field(default_factory=list)
