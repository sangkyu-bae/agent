"""Parser Factory for creating PDF parser instances.

Provides factory methods to create parser implementations
based on parser type configuration.
"""
from enum import Enum
from typing import Optional

from src.domain.parser.interfaces import PDFParserInterface
from src.infrastructure.parser.pymupdf_parser import PyMuPDFParser
from src.infrastructure.parser.llamaparser import LlamaParserAdapter


class ParserType(Enum):
    """Supported parser types."""

    PYMUPDF = "pymupdf"
    LLAMAPARSER = "llamaparser"

    @classmethod
    def from_string(cls, type_str: str) -> "ParserType":
        """Create ParserType from string (case-insensitive).

        Args:
            type_str: String representation of the parser type

        Returns:
            ParserType enum value

        Raises:
            ValueError: If type_str is not a valid parser type
        """
        type_lower = type_str.lower()
        for member in cls:
            if member.value == type_lower:
                return member
        raise ValueError(f"Unknown parser type: {type_str}")


class ParserFactory:
    """Factory for creating PDF parser instances."""

    @staticmethod
    def create(
        parser_type: ParserType,
        api_key: Optional[str] = None,
    ) -> PDFParserInterface:
        """Create a parser instance for the given type.

        Args:
            parser_type: The parser type to create
            api_key: API key for cloud-based parsers (required for LLAMAPARSER)

        Returns:
            A PDFParserInterface implementation

        Raises:
            ValueError: If required parameters are missing
        """
        if parser_type == ParserType.PYMUPDF:
            return PyMuPDFParser()

        if parser_type == ParserType.LLAMAPARSER:
            if not api_key:
                raise ValueError("api_key is required for LlamaParser")
            return LlamaParserAdapter(api_key=api_key)

        raise ValueError(f"Unsupported parser type: {parser_type}")

    @staticmethod
    def create_from_string(
        type_str: str,
        api_key: Optional[str] = None,
    ) -> PDFParserInterface:
        """Create a parser instance using string type name.

        Args:
            type_str: The parser type name as string (e.g., "pymupdf")
            api_key: API key for cloud-based parsers

        Returns:
            A PDFParserInterface implementation
        """
        parser_type = ParserType.from_string(type_str)
        return ParserFactory.create(parser_type, api_key=api_key)
