"""Upload schema for document upload response."""
from typing import List

from pydantic import BaseModel

from src.domain.pipeline.enums.document_category import DocumentCategory


class DocumentUploadResponse(BaseModel):
    """Response schema for document upload.

    Attributes:
        document_id: Unique identifier for the uploaded document.
        filename: Original filename of the uploaded document.
        category: Classified document category.
        category_confidence: Confidence score for classification.
        total_pages: Total number of pages in the document.
        chunk_count: Number of chunks created.
        stored_ids: List of stored chunk IDs.
        status: Processing status (pending, parsing, classifying, chunking, storing, completed, failed).
        errors: List of error messages if any.
    """

    document_id: str
    filename: str
    category: DocumentCategory
    category_confidence: float
    total_pages: int
    chunk_count: int
    stored_ids: List[str]
    status: str
    errors: List[str]
