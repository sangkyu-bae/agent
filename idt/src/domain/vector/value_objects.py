"""Value objects for vector domain.

These are immutable objects that represent domain concepts with validation.
No external API calls (LLM, Qdrant, etc.) are allowed in domain layer.
"""
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Dict, Optional


@dataclass(frozen=True)
class DocumentId:
    """Represents a document identifier in the vector store."""

    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("DocumentId cannot be empty")


class DocumentType(Enum):
    """Document types for categorizing documents in the RAG system.

    These types represent different categories of documents
    commonly used in financial/policy document systems.
    """

    POLICY = "policy"
    FAQ = "faq"
    MANUAL = "manual"
    NOTICE = "notice"

    @classmethod
    def from_string(cls, type_str: str) -> "DocumentType":
        """Create DocumentType from string value (case-insensitive).

        Args:
            type_str: String representation of the document type

        Returns:
            DocumentType enum value

        Raises:
            ValueError: If type_str is not a valid document type
        """
        type_lower = type_str.lower()
        for member in cls:
            if member.value == type_lower:
                return member
        raise ValueError(f"Invalid document type: {type_str}")


@dataclass(frozen=True)
class DateRange:
    """Represents a date range for filtering documents.

    Both start_date and end_date are inclusive.
    """

    start_date: date
    end_date: date

    def __post_init__(self) -> None:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be >= start_date")

    def contains(self, check_date: date) -> bool:
        """Check if a date falls within this range (inclusive).

        Args:
            check_date: The date to check

        Returns:
            True if check_date is within the range, False otherwise
        """
        return self.start_date <= check_date <= self.end_date


@dataclass(frozen=True)
class SearchFilter:
    """Filter conditions for vector search.

    Combines multiple filter conditions that can be applied
    during vector search operations.
    """

    document_type: Optional[DocumentType] = None
    date_range: Optional[DateRange] = None
    metadata: Dict[str, str] = field(default_factory=dict)

    def is_empty(self) -> bool:
        """Check if the filter has no conditions set.

        Returns:
            True if no filter conditions are set, False otherwise
        """
        return (
            self.document_type is None
            and self.date_range is None
            and len(self.metadata) == 0
        )
