"""Tests for parser factory implementation.

Infrastructure tests use mocks as per CLAUDE.md rules.
"""
import pytest
from unittest.mock import patch

from src.infrastructure.parser.parser_factory import (
    ParserFactory,
    ParserType,
)
from src.domain.parser.interfaces import PDFParserInterface
from src.infrastructure.parser.pymupdf_parser import PyMuPDFParser
from src.infrastructure.parser.llamaparser import LlamaParserAdapter


class TestParserType:
    """Tests for ParserType enum."""

    def test_pymupdf_type(self) -> None:
        """PYMUPDF type should have value 'pymupdf'."""
        assert ParserType.PYMUPDF.value == "pymupdf"

    def test_llamaparser_type(self) -> None:
        """LLAMAPARSER type should have value 'llamaparser'."""
        assert ParserType.LLAMAPARSER.value == "llamaparser"

    def test_from_string_pymupdf(self) -> None:
        """Should create PYMUPDF from string."""
        parser_type = ParserType.from_string("pymupdf")
        assert parser_type == ParserType.PYMUPDF

    def test_from_string_llamaparser(self) -> None:
        """Should create LLAMAPARSER from string."""
        parser_type = ParserType.from_string("llamaparser")
        assert parser_type == ParserType.LLAMAPARSER

    def test_from_string_case_insensitive(self) -> None:
        """from_string should be case-insensitive."""
        assert ParserType.from_string("PYMUPDF") == ParserType.PYMUPDF
        assert ParserType.from_string("PyMuPDF") == ParserType.PYMUPDF

    def test_from_string_invalid_raises_error(self) -> None:
        """Invalid string should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown parser type"):
            ParserType.from_string("invalid")


class TestParserFactoryCreate:
    """Tests for ParserFactory.create method."""

    def test_create_pymupdf_parser(self) -> None:
        """Should create PyMuPDFParser for PYMUPDF type."""
        parser = ParserFactory.create(ParserType.PYMUPDF)
        assert isinstance(parser, PyMuPDFParser)
        assert isinstance(parser, PDFParserInterface)

    def test_create_llamaparser_requires_api_key(self) -> None:
        """LLAMAPARSER should require api_key parameter."""
        with pytest.raises(ValueError, match="api_key is required"):
            ParserFactory.create(ParserType.LLAMAPARSER)

    def test_create_llamaparser_with_api_key(self) -> None:
        """Should create LlamaParserAdapter with api_key."""
        with patch("src.infrastructure.parser.llamaparser.LlamaParse"):
            parser = ParserFactory.create(
                ParserType.LLAMAPARSER, api_key="test-api-key"
            )
            assert isinstance(parser, LlamaParserAdapter)
            assert isinstance(parser, PDFParserInterface)

    def test_created_parser_is_functional(self) -> None:
        """Created parser should be functional."""
        parser = ParserFactory.create(ParserType.PYMUPDF)
        assert parser.get_parser_name() == "pymupdf"
        assert parser.supports_ocr() is False


class TestParserFactoryCreateFromString:
    """Tests for ParserFactory.create_from_string method."""

    def test_create_from_string_pymupdf(self) -> None:
        """Should create parser from string 'pymupdf'."""
        parser = ParserFactory.create_from_string("pymupdf")
        assert isinstance(parser, PyMuPDFParser)

    def test_create_from_string_case_insensitive(self) -> None:
        """Should be case-insensitive."""
        parser = ParserFactory.create_from_string("PYMUPDF")
        assert isinstance(parser, PyMuPDFParser)

    def test_create_from_string_invalid_raises_error(self) -> None:
        """Invalid string should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown parser type"):
            ParserFactory.create_from_string("invalid")

    def test_create_from_string_llamaparser_requires_api_key(self) -> None:
        """LLAMAPARSER should require api_key."""
        with pytest.raises(ValueError, match="api_key is required"):
            ParserFactory.create_from_string("llamaparser")

    def test_create_from_string_llamaparser_with_api_key(self) -> None:
        """Should create LlamaParser from string with api_key."""
        with patch("src.infrastructure.parser.llamaparser.LlamaParse"):
            parser = ParserFactory.create_from_string(
                "llamaparser", api_key="test-api-key"
            )
            assert isinstance(parser, LlamaParserAdapter)
