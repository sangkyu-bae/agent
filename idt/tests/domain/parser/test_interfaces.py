"""Tests for parser domain interfaces.

TDD: These tests are written first before implementation.
Domain tests use NO mocks as per CLAUDE.md rules.
"""
import pytest
from abc import ABC
from typing import List

from src.domain.parser.interfaces import PDFParserInterface
from src.domain.parser.value_objects import ParserConfig


class TestPDFParserInterface:
    """Tests for PDFParserInterface abstract class."""

    def test_is_abstract_class(self) -> None:
        """PDFParserInterface should be an ABC."""
        assert issubclass(PDFParserInterface, ABC)

    def test_cannot_instantiate_directly(self) -> None:
        """Should not be able to instantiate abstract class directly."""
        with pytest.raises(TypeError):
            PDFParserInterface()

    def test_has_parse_method(self) -> None:
        """Should have abstract parse method."""
        assert hasattr(PDFParserInterface, "parse")
        assert callable(getattr(PDFParserInterface, "parse"))

    def test_has_parse_bytes_method(self) -> None:
        """Should have abstract parse_bytes method."""
        assert hasattr(PDFParserInterface, "parse_bytes")
        assert callable(getattr(PDFParserInterface, "parse_bytes"))

    def test_has_get_parser_name_method(self) -> None:
        """Should have abstract get_parser_name method."""
        assert hasattr(PDFParserInterface, "get_parser_name")
        assert callable(getattr(PDFParserInterface, "get_parser_name"))

    def test_has_supports_ocr_method(self) -> None:
        """Should have abstract supports_ocr method."""
        assert hasattr(PDFParserInterface, "supports_ocr")
        assert callable(getattr(PDFParserInterface, "supports_ocr"))


class TestPDFParserInterfaceImplementation:
    """Test that concrete implementations must implement all methods."""

    def test_incomplete_implementation_raises_error(self) -> None:
        """Incomplete implementation should raise TypeError."""

        class IncompleteParser(PDFParserInterface):
            pass

        with pytest.raises(TypeError):
            IncompleteParser()

    def test_partial_implementation_raises_error(self) -> None:
        """Partial implementation should raise TypeError."""

        class PartialParser(PDFParserInterface):
            def parse(
                self,
                file_path: str,
                user_id: str,
                config: ParserConfig | None = None,
            ) -> List:
                return []

        with pytest.raises(TypeError):
            PartialParser()

    def test_complete_implementation_can_be_instantiated(self) -> None:
        """Complete implementation should be instantiable."""

        class CompleteParser(PDFParserInterface):
            def parse(
                self,
                file_path: str,
                user_id: str,
                config: ParserConfig | None = None,
            ) -> List:
                return []

            def parse_bytes(
                self,
                file_bytes: bytes,
                filename: str,
                user_id: str,
                config: ParserConfig | None = None,
            ) -> List:
                return []

            def get_parser_name(self) -> str:
                return "test"

            def supports_ocr(self) -> bool:
                return False

        parser = CompleteParser()
        assert parser is not None
        assert parser.get_parser_name() == "test"
        assert parser.supports_ocr() is False
