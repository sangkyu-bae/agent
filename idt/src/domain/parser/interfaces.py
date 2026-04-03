"""Domain interfaces for PDF parsing.

These are abstract base classes that define contracts for PDF parsers.
Implementations live in infrastructure layer.

No external API calls or LangChain usage allowed in domain layer.
"""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional

from src.domain.parser.value_objects import ParserConfig

if TYPE_CHECKING:
    from langchain_core.documents import Document


class PDFParserInterface(ABC):
    """Abstract interface for PDF parsing operations.

    Implementations should wrap specific PDF parsing libraries
    (e.g., PyMuPDF, LlamaParse) in the infrastructure layer.
    """

    @abstractmethod
    def parse(
        self,
        file_path: str,
        user_id: str,
        config: Optional[ParserConfig] = None,
    ) -> List["Document"]:
        """Parse a PDF file from the filesystem.

        Args:
            file_path: Path to the PDF file
            user_id: ID of the user uploading the document
            config: Optional parser configuration

        Returns:
            List of LangChain Document objects with metadata
        """
        pass

    @abstractmethod
    def parse_bytes(
        self,
        file_bytes: bytes,
        filename: str,
        user_id: str,
        config: Optional[ParserConfig] = None,
    ) -> List["Document"]:
        """Parse a PDF from bytes.

        Args:
            file_bytes: Raw PDF file content
            filename: Original filename for metadata
            user_id: ID of the user uploading the document
            config: Optional parser configuration

        Returns:
            List of LangChain Document objects with metadata
        """
        pass

    @abstractmethod
    def get_parser_name(self) -> str:
        """Return the name of this parser implementation.

        Returns:
            Parser name (e.g., "pymupdf", "llamaparser")
        """
        pass

    @abstractmethod
    def supports_ocr(self) -> bool:
        """Check if this parser supports OCR for scanned documents.

        Returns:
            True if OCR is supported, False otherwise
        """
        pass
