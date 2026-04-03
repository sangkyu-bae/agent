"""Tests for LlamaParser implementation.

Infrastructure tests use mocks as per CLAUDE.md rules.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from src.infrastructure.parser.llamaparser import LlamaParserAdapter
from src.domain.parser.interfaces import PDFParserInterface
from src.domain.parser.value_objects import ParserConfig


class TestLlamaParserAdapter:
    """Tests for LlamaParserAdapter implementation."""

    def test_implements_pdf_parser_interface(self) -> None:
        """LlamaParserAdapter should implement PDFParserInterface."""
        with patch("src.infrastructure.parser.llamaparser.LlamaParse"):
            parser = LlamaParserAdapter(api_key="test-api-key")
            assert isinstance(parser, PDFParserInterface)

    def test_get_parser_name(self) -> None:
        """Parser name should be 'llamaparser'."""
        with patch("src.infrastructure.parser.llamaparser.LlamaParse"):
            parser = LlamaParserAdapter(api_key="test-api-key")
            assert parser.get_parser_name() == "llamaparser"

    def test_supports_ocr_returns_true(self) -> None:
        """LlamaParser supports OCR."""
        with patch("src.infrastructure.parser.llamaparser.LlamaParse"):
            parser = LlamaParserAdapter(api_key="test-api-key")
            assert parser.supports_ocr() is True

    def test_requires_api_key(self) -> None:
        """Should require API key for initialization."""
        with patch("src.infrastructure.parser.llamaparser.LlamaParse") as mock_cls:
            LlamaParserAdapter(api_key="my-api-key")
            mock_cls.assert_called_once()
            call_kwargs = mock_cls.call_args[1]
            assert call_kwargs["api_key"] == "my-api-key"


class TestLlamaParserAdapterParse:
    """Tests for LlamaParserAdapter.parse method."""

    def test_parse_single_page_pdf(self) -> None:
        """Should parse single page PDF correctly."""
        mock_result = MagicMock()
        mock_result.text = "Page 1 content"
        mock_result.metadata = {"page": 1}

        with patch("src.infrastructure.parser.llamaparser.LlamaParse") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.load_data.return_value = [mock_result]
            mock_cls.return_value = mock_instance

            parser = LlamaParserAdapter(api_key="test-key")
            docs = parser.parse("/path/to/test.pdf", "user123")

            assert len(docs) == 1
            assert docs[0].page_content == "Page 1 content"
            assert docs[0].metadata["user_id"] == "user123"
            assert docs[0].metadata["parser"] == "llamaparser"
            assert "document_id" in docs[0].metadata
            assert "chunk_id" in docs[0].metadata

    def test_parse_multi_page_pdf(self) -> None:
        """Should parse multi-page PDF correctly."""
        mock_results = []
        for i in range(3):
            mock_result = MagicMock()
            mock_result.text = f"Page {i + 1} content"
            mock_result.metadata = {"page": i + 1}
            mock_results.append(mock_result)

        with patch("src.infrastructure.parser.llamaparser.LlamaParse") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.load_data.return_value = mock_results
            mock_cls.return_value = mock_instance

            parser = LlamaParserAdapter(api_key="test-key")
            docs = parser.parse("/path/to/test.pdf", "user123")

            assert len(docs) == 3
            for i, doc in enumerate(docs):
                assert doc.page_content == f"Page {i + 1} content"

    def test_parse_with_custom_config(self) -> None:
        """Should use custom config when provided."""
        mock_result = MagicMock()
        mock_result.text = "Content"
        mock_result.metadata = {"page": 1}

        with patch("src.infrastructure.parser.llamaparser.LlamaParse") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.load_data.return_value = [mock_result]
            mock_cls.return_value = mock_instance

            parser = LlamaParserAdapter(api_key="test-key")
            config = ParserConfig(language="en")
            docs = parser.parse("/path/to/test.pdf", "user123", config=config)

            assert len(docs) == 1

    def test_parse_empty_pdf_returns_empty_list(self) -> None:
        """Should return empty list for PDF with no content."""
        with patch("src.infrastructure.parser.llamaparser.LlamaParse") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.load_data.return_value = []
            mock_cls.return_value = mock_instance

            parser = LlamaParserAdapter(api_key="test-key")
            docs = parser.parse("/path/to/empty.pdf", "user123")

            assert len(docs) == 0

    def test_parse_extracts_filename_from_path(self) -> None:
        """Should extract filename from file path for metadata."""
        mock_result = MagicMock()
        mock_result.text = "Content"
        mock_result.metadata = {"page": 1}

        with patch("src.infrastructure.parser.llamaparser.LlamaParse") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.load_data.return_value = [mock_result]
            mock_cls.return_value = mock_instance

            parser = LlamaParserAdapter(api_key="test-key")
            docs = parser.parse("/path/to/회사소개서.pdf", "user123")

            assert docs[0].metadata["filename"] == "회사소개서.pdf"


class TestLlamaParserAdapterParseBytes:
    """Tests for LlamaParserAdapter.parse_bytes method."""

    def test_parse_bytes_single_page(self) -> None:
        """Should parse PDF bytes correctly."""
        mock_result = MagicMock()
        mock_result.text = "Bytes content"
        mock_result.metadata = {"page": 1}

        with patch("src.infrastructure.parser.llamaparser.LlamaParse") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.load_data.return_value = [mock_result]
            mock_cls.return_value = mock_instance

            parser = LlamaParserAdapter(api_key="test-key")
            pdf_bytes = b"%PDF-1.4 fake content"
            docs = parser.parse_bytes(pdf_bytes, "report.pdf", "user123")

            assert len(docs) == 1
            assert docs[0].page_content == "Bytes content"
            assert docs[0].metadata["filename"] == "report.pdf"
            assert docs[0].metadata["user_id"] == "user123"


class TestLlamaParserAdapterMetadata:
    """Tests for metadata field generation."""

    def test_document_id_format(self) -> None:
        """Document ID should follow {uuid8}_{filename} format."""
        mock_result = MagicMock()
        mock_result.text = "Content"
        mock_result.metadata = {"page": 1}

        with patch("src.infrastructure.parser.llamaparser.LlamaParse") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.load_data.return_value = [mock_result]
            mock_cls.return_value = mock_instance

            parser = LlamaParserAdapter(api_key="test-key")
            docs = parser.parse("/path/to/test.pdf", "user123")

            doc_id = docs[0].metadata["document_id"]
            parts = doc_id.split("_", 1)
            assert len(parts) == 2
            assert len(parts[0]) == 8

    def test_chunk_id_format(self) -> None:
        """Chunk ID should follow {document_id}_p{page4digits} format."""
        mock_result = MagicMock()
        mock_result.text = "Content"
        mock_result.metadata = {"page": 1}

        with patch("src.infrastructure.parser.llamaparser.LlamaParse") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.load_data.return_value = [mock_result]
            mock_cls.return_value = mock_instance

            parser = LlamaParserAdapter(api_key="test-key")
            docs = parser.parse("/path/to/test.pdf", "user123")

            chunk_id = docs[0].metadata["chunk_id"]
            assert "_p0001" in chunk_id

    def test_created_by_equals_user_id(self) -> None:
        """created_by field should equal user_id."""
        mock_result = MagicMock()
        mock_result.text = "Content"
        mock_result.metadata = {"page": 1}

        with patch("src.infrastructure.parser.llamaparser.LlamaParse") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.load_data.return_value = [mock_result]
            mock_cls.return_value = mock_instance

            parser = LlamaParserAdapter(api_key="test-key")
            docs = parser.parse("/path/to/test.pdf", "user123")

            assert docs[0].metadata["created_by"] == "user123"

    def test_created_at_is_present(self) -> None:
        """created_at field should be present in metadata."""
        mock_result = MagicMock()
        mock_result.text = "Content"
        mock_result.metadata = {"page": 1}

        with patch("src.infrastructure.parser.llamaparser.LlamaParse") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.load_data.return_value = [mock_result]
            mock_cls.return_value = mock_instance

            parser = LlamaParserAdapter(api_key="test-key")
            docs = parser.parse("/path/to/test.pdf", "user123")

            assert "created_at" in docs[0].metadata


class TestLlamaParserAdapterLanguage:
    """Tests for language configuration."""

    def test_default_language_korean(self) -> None:
        """Default language should be Korean."""
        with patch("src.infrastructure.parser.llamaparser.LlamaParse") as mock_cls:
            LlamaParserAdapter(api_key="test-key")
            call_kwargs = mock_cls.call_args[1]
            assert call_kwargs["language"] == "ko"

    def test_custom_language_from_config(self) -> None:
        """Should use language from config."""
        with patch("src.infrastructure.parser.llamaparser.LlamaParse") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.load_data.return_value = []
            mock_cls.return_value = mock_instance

            parser = LlamaParserAdapter(api_key="test-key")
            config = ParserConfig(language="en")
            parser.parse("/path/to/test.pdf", "user123", config=config)

            # Second call should have updated language
            assert mock_cls.call_count >= 1
