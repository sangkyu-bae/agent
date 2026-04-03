"""Domain schemas for PDF parsing operations.

These are pure data transfer objects with no external dependencies.
No LangChain imports at runtime (TYPE_CHECKING only).
"""
from typing import TYPE_CHECKING, Any, List, Optional

from pydantic import BaseModel, field_validator

if TYPE_CHECKING:
    pass


class ParseDocumentRequest(BaseModel):
    """Request schema for PDF parsing operations.

    Attributes:
        filename: Original filename of the PDF
        user_id: ID of the user requesting the parse
        request_id: Unique ID for request tracing (LOG-001)
        file_path: Path to PDF file on filesystem (mutually exclusive with file_bytes)
        file_bytes: Raw PDF bytes (mutually exclusive with file_path)
    """

    filename: str
    user_id: str
    request_id: str
    file_path: Optional[str] = None
    file_bytes: Optional[bytes] = None

    @field_validator("filename")
    @classmethod
    def filename_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("filename cannot be empty")
        return v

    @field_validator("user_id")
    @classmethod
    def user_id_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("user_id cannot be empty")
        return v

    @field_validator("request_id")
    @classmethod
    def request_id_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("request_id cannot be empty")
        return v

    model_config = {"arbitrary_types_allowed": True}


class ParseDocumentResult(BaseModel):
    """Result schema for PDF parsing operations.

    Attributes:
        document_id: Generated unique document ID
        filename: Original filename
        user_id: ID of the user who requested the parse
        total_pages: Total number of parsed pages
        parser_used: Name of the parser that was used
        documents: List of LangChain Document objects
        request_id: Request ID for tracing (LOG-001)
    """

    document_id: str
    filename: str
    user_id: str
    total_pages: int
    parser_used: str
    documents: List[Any]
    request_id: str

    model_config = {"arbitrary_types_allowed": True}
