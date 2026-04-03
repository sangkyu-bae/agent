"""Tests for PyMuPDF parser implementation.

Infrastructure tests use mocks as per CLAUDE.md rules.
"""
import pytest
from unittest.mock import MagicMock, patch, mock_open

from src.infrastructure.parser.pymupdf_parser import PyMuPDFParser
from src.domain.parser.interfaces import PDFParserInterface
from src.domain.parser.value_objects import ParserConfig


class TestPyMuPDFParser:
    """Tests for PyMuPDFParser implementation."""

    def test_implements_pdf_parser_interface(self) -> None:
        """PyMuPDFParser should implement PDFParserInterface."""
        parser = PyMuPDFParser()
        assert isinstance(parser, PDFParserInterface)

    def test_get_parser_name(self) -> None:
        """Parser name should be 'pymupdf'."""
        parser = PyMuPDFParser()
        assert parser.get_parser_name() == "pymupdf"

    def test_supports_ocr_returns_false(self) -> None:
        """PyMuPDF basic implementation does not support OCR."""
        parser = PyMuPDFParser()
        assert parser.supports_ocr() is False


class TestPyMuPDFParserParse:
    """Tests for PyMuPDFParser.parse method."""

    @pytest.fixture
    def mock_fitz(self) -> MagicMock:
        """Create a mock fitz (PyMuPDF) module."""
        mock = MagicMock()
        return mock

    def test_parse_single_page_pdf(self) -> None:
        """Should parse single page PDF correctly."""
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Page 1 content"

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.page_count = 1

        with patch(
            "src.infrastructure.parser.pymupdf_parser.fitz.open"
        ) as mock_open_pdf:
            mock_open_pdf.return_value.__enter__ = MagicMock(return_value=mock_doc)
            mock_open_pdf.return_value.__exit__ = MagicMock(return_value=False)

            parser = PyMuPDFParser()
            docs = parser.parse("/path/to/test.pdf", "user123")

            assert len(docs) == 1
            assert docs[0].page_content == "Page 1 content"
            assert docs[0].metadata["page"] == 1
            assert docs[0].metadata["total_pages"] == 1
            assert docs[0].metadata["user_id"] == "user123"
            assert docs[0].metadata["parser"] == "pymupdf"
            assert "document_id" in docs[0].metadata
            assert "chunk_id" in docs[0].metadata

    def test_parse_multi_page_pdf(self) -> None:
        """Should parse multi-page PDF correctly."""
        mock_pages = []
        for i in range(3):
            mock_page = MagicMock()
            mock_page.get_text.return_value = f"Page {i + 1} content"
            mock_pages.append(mock_page)

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=3)
        mock_doc.__iter__ = MagicMock(return_value=iter(mock_pages))
        mock_doc.page_count = 3

        with patch(
            "src.infrastructure.parser.pymupdf_parser.fitz.open"
        ) as mock_open_pdf:
            mock_open_pdf.return_value.__enter__ = MagicMock(return_value=mock_doc)
            mock_open_pdf.return_value.__exit__ = MagicMock(return_value=False)

            parser = PyMuPDFParser()
            docs = parser.parse("/path/to/test.pdf", "user123")

            assert len(docs) == 3
            for i, doc in enumerate(docs):
                assert doc.page_content == f"Page {i + 1} content"
                assert doc.metadata["page"] == i + 1
                assert doc.metadata["total_pages"] == 3

    def test_parse_with_custom_config(self) -> None:
        """Should use custom config when provided."""
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Test content"

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.page_count = 1

        with patch(
            "src.infrastructure.parser.pymupdf_parser.fitz.open"
        ) as mock_open_pdf:
            mock_open_pdf.return_value.__enter__ = MagicMock(return_value=mock_doc)
            mock_open_pdf.return_value.__exit__ = MagicMock(return_value=False)

            parser = PyMuPDFParser()
            config = ParserConfig(chunk_size=500, language="en")
            docs = parser.parse("/path/to/test.pdf", "user123", config=config)

            assert len(docs) == 1

    def test_parse_empty_pdf_returns_empty_list(self) -> None:
        """Should return empty list for PDF with no pages."""
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=0)
        mock_doc.__iter__ = MagicMock(return_value=iter([]))
        mock_doc.page_count = 0

        with patch(
            "src.infrastructure.parser.pymupdf_parser.fitz.open"
        ) as mock_open_pdf:
            mock_open_pdf.return_value.__enter__ = MagicMock(return_value=mock_doc)
            mock_open_pdf.return_value.__exit__ = MagicMock(return_value=False)

            parser = PyMuPDFParser()
            docs = parser.parse("/path/to/empty.pdf", "user123")

            assert len(docs) == 0

    def test_parse_nonexistent_file_raises_error(self) -> None:
        """Should raise FileNotFoundError for non-existent file."""
        with patch(
            "src.infrastructure.parser.pymupdf_parser.fitz.open"
        ) as mock_open_pdf:
            mock_open_pdf.side_effect = FileNotFoundError("No such file")

            parser = PyMuPDFParser()
            with pytest.raises(FileNotFoundError):
                parser.parse("/path/to/nonexistent.pdf", "user123")

    def test_parse_extracts_filename_from_path(self) -> None:
        """Should extract filename from file path for metadata."""
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Content"

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.page_count = 1

        with patch(
            "src.infrastructure.parser.pymupdf_parser.fitz.open"
        ) as mock_open_pdf:
            mock_open_pdf.return_value.__enter__ = MagicMock(return_value=mock_doc)
            mock_open_pdf.return_value.__exit__ = MagicMock(return_value=False)

            parser = PyMuPDFParser()
            docs = parser.parse("/path/to/회사소개서.pdf", "user123")

            assert docs[0].metadata["filename"] == "회사소개서.pdf"


class TestPyMuPDFParserParseBytes:
    """Tests for PyMuPDFParser.parse_bytes method."""

    def test_parse_bytes_single_page(self) -> None:
        """Should parse PDF bytes correctly."""
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Bytes content"

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.page_count = 1

        with patch(
            "src.infrastructure.parser.pymupdf_parser.fitz.open"
        ) as mock_open_pdf:
            mock_open_pdf.return_value.__enter__ = MagicMock(return_value=mock_doc)
            mock_open_pdf.return_value.__exit__ = MagicMock(return_value=False)

            parser = PyMuPDFParser()
            pdf_bytes = b"%PDF-1.4 fake content"
            docs = parser.parse_bytes(pdf_bytes, "report.pdf", "user123")

            assert len(docs) == 1
            assert docs[0].page_content == "Bytes content"
            assert docs[0].metadata["filename"] == "report.pdf"
            assert docs[0].metadata["user_id"] == "user123"

    def test_parse_bytes_uses_stream_type(self) -> None:
        """Should open PDF with stream type for bytes."""
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=0)
        mock_doc.__iter__ = MagicMock(return_value=iter([]))
        mock_doc.page_count = 0

        with patch(
            "src.infrastructure.parser.pymupdf_parser.fitz.open"
        ) as mock_open_pdf:
            mock_open_pdf.return_value.__enter__ = MagicMock(return_value=mock_doc)
            mock_open_pdf.return_value.__exit__ = MagicMock(return_value=False)

            parser = PyMuPDFParser()
            pdf_bytes = b"%PDF-1.4 fake content"
            parser.parse_bytes(pdf_bytes, "test.pdf", "user123")

            mock_open_pdf.assert_called_once()
            call_kwargs = mock_open_pdf.call_args
            assert call_kwargs[1].get("stream") == pdf_bytes
            assert call_kwargs[1].get("filetype") == "pdf"


class TestPyMuPDFParserMetadata:
    """Tests for metadata field generation."""

    def test_document_id_format(self) -> None:
        """Document ID should follow {uuid8}_{filename} format."""
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Content"

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.page_count = 1

        with patch(
            "src.infrastructure.parser.pymupdf_parser.fitz.open"
        ) as mock_open_pdf:
            mock_open_pdf.return_value.__enter__ = MagicMock(return_value=mock_doc)
            mock_open_pdf.return_value.__exit__ = MagicMock(return_value=False)

            parser = PyMuPDFParser()
            docs = parser.parse("/path/to/test.pdf", "user123")

            doc_id = docs[0].metadata["document_id"]
            parts = doc_id.split("_", 1)
            assert len(parts) == 2
            assert len(parts[0]) == 8  # uuid 8 chars
            assert parts[1] == "test"  # filename without .pdf

    def test_chunk_id_format(self) -> None:
        """Chunk ID should follow {document_id}_p{page4digits} format."""
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Content"

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.page_count = 1

        with patch(
            "src.infrastructure.parser.pymupdf_parser.fitz.open"
        ) as mock_open_pdf:
            mock_open_pdf.return_value.__enter__ = MagicMock(return_value=mock_doc)
            mock_open_pdf.return_value.__exit__ = MagicMock(return_value=False)

            parser = PyMuPDFParser()
            docs = parser.parse("/path/to/test.pdf", "user123")

            chunk_id = docs[0].metadata["chunk_id"]
            assert "_p0001" in chunk_id

    def test_created_by_equals_user_id(self) -> None:
        """created_by field should equal user_id."""
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Content"

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.page_count = 1

        with patch(
            "src.infrastructure.parser.pymupdf_parser.fitz.open"
        ) as mock_open_pdf:
            mock_open_pdf.return_value.__enter__ = MagicMock(return_value=mock_doc)
            mock_open_pdf.return_value.__exit__ = MagicMock(return_value=False)

            parser = PyMuPDFParser()
            docs = parser.parse("/path/to/test.pdf", "user123")

            assert docs[0].metadata["created_by"] == "user123"

    def test_created_at_is_present(self) -> None:
        """created_at field should be present in metadata."""
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Content"

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.page_count = 1

        with patch(
            "src.infrastructure.parser.pymupdf_parser.fitz.open"
        ) as mock_open_pdf:
            mock_open_pdf.return_value.__enter__ = MagicMock(return_value=mock_doc)
            mock_open_pdf.return_value.__exit__ = MagicMock(return_value=False)

            parser = PyMuPDFParser()
            docs = parser.parse("/path/to/test.pdf", "user123")

            assert "created_at" in docs[0].metadata
