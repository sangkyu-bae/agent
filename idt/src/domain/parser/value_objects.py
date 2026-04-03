"""Value objects for parser domain.

These are immutable objects that represent parsing configuration and metadata.
No external API calls (LLM, Qdrant, etc.) are allowed in domain layer.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Set

VALID_LANGUAGE_CODES: Set[str] = {
    "ko", "en", "ja", "zh", "de", "fr", "es", "it", "pt", "ru",
    "ar", "hi", "th", "vi", "id", "ms", "nl", "pl", "tr", "sv",
}


@dataclass(frozen=True)
class ParserConfig:
    """Configuration for PDF parsing operations.

    Attributes:
        chunk_size: Maximum characters per chunk (must be > 0)
        chunk_overlap: Overlap characters between chunks (must be >= 0)
        extract_images: Whether to extract images from PDF
        extract_tables: Whether to extract tables from PDF
        ocr_enabled: Whether to use OCR for scanned documents
        language: ISO 639-1 language code for content
    """

    chunk_size: int = 1000
    chunk_overlap: int = 200
    extract_images: bool = False
    extract_tables: bool = True
    ocr_enabled: bool = False
    language: str = "ko"

    def __post_init__(self) -> None:
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        if self.chunk_overlap < 0:
            raise ValueError("chunk_overlap must be >= 0")
        if self.chunk_size <= self.chunk_overlap:
            raise ValueError("chunk_size must be > chunk_overlap")
        if self.language not in VALID_LANGUAGE_CODES:
            raise ValueError(f"Invalid language code: {self.language}")


def generate_document_id(filename: str) -> str:
    """Generate a unique document ID from filename.

    Format: {uuid8chars}_{safe_filename}

    Args:
        filename: Original filename (with or without .pdf extension)

    Returns:
        Unique document ID string
    """
    unique_id = uuid.uuid4().hex[:8]
    safe_filename = filename.replace(" ", "_").replace(".pdf", "")
    return f"{unique_id}_{safe_filename}"


def generate_chunk_id(document_id: str, page: int) -> str:
    """Generate a chunk ID from document ID and page number.

    Format: {document_id}_p{page4digits}

    Args:
        document_id: The parent document ID
        page: Page number (1-indexed)

    Returns:
        Chunk ID string
    """
    return f"{document_id}_p{page:04d}"


@dataclass(frozen=True)
class DocumentMetadata:
    """Metadata for a parsed document chunk.

    Attributes:
        filename: Original filename
        user_id: ID of user who uploaded the document
        page: Current page number (1-indexed)
        total_pages: Total pages in the document
        parser: Name of parser used
        chunk_index: Index of chunk within page (default 0)
        document_id: Auto-generated unique document ID
        chunk_id: Auto-generated chunk ID
        created_at: Timestamp when metadata was created
        created_by: Alias for user_id
    """

    filename: str
    user_id: str
    page: int
    total_pages: int
    parser: str
    chunk_index: int = 0
    document_id: str = field(default="")
    chunk_id: str = field(default="")
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str = field(default="")

    def __post_init__(self) -> None:
        if not self.filename or not self.filename.strip():
            raise ValueError("filename cannot be empty")
        if not self.user_id or not self.user_id.strip():
            raise ValueError("user_id cannot be empty")
        if not self.parser or not self.parser.strip():
            raise ValueError("parser cannot be empty")
        if self.page < 1:
            raise ValueError("page must be >= 1")
        if self.total_pages < 1:
            raise ValueError("total_pages must be >= 1")
        if self.page > self.total_pages:
            raise ValueError("page cannot exceed total_pages")

        # Auto-generate IDs if not provided (frozen=True requires object.__setattr__)
        if not self.document_id:
            object.__setattr__(
                self, "document_id", generate_document_id(self.filename)
            )
        if not self.chunk_id:
            object.__setattr__(
                self, "chunk_id", generate_chunk_id(self.document_id, self.page)
            )
        if not self.created_by:
            object.__setattr__(self, "created_by", self.user_id)

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary for LangChain Document.

        Returns:
            Dictionary with all metadata fields
        """
        return {
            "filename": self.filename,
            "user_id": self.user_id,
            "page": self.page,
            "total_pages": self.total_pages,
            "parser": self.parser,
            "chunk_index": self.chunk_index,
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
        }
