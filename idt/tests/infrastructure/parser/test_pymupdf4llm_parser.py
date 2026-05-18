"""Tests for PyMuPDF4LLM parser implementation."""
from typing import Any, Dict, List

import pytest
from unittest.mock import MagicMock, patch

from src.domain.parser.interfaces import PDFParserInterface
from src.domain.parser.value_objects import ParserConfig


def _make_page_chunks(
    pages: List[str],
    start_page: int = 0,
) -> List[Dict[str, Any]]:
    return [
        {
            "metadata": {"page": start_page + i, "width": 595.0, "height": 842.0},
            "text": text,
            "tables": [],
            "images": [],
        }
        for i, text in enumerate(pages)
    ]


def _setup_mock_fitz(mock_fitz: MagicMock, page_count: int) -> MagicMock:
    mock_doc = MagicMock()
    mock_doc.page_count = page_count
    mock_fitz.open.return_value.__enter__ = MagicMock(return_value=mock_doc)
    mock_fitz.open.return_value.__exit__ = MagicMock(return_value=False)
    return mock_doc


class TestPyMuPDF4LLMParserInterface:

    def test_implements_pdf_parser_interface(self) -> None:
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        assert isinstance(parser, PDFParserInterface)

    def test_get_parser_name(self) -> None:
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        assert parser.get_parser_name() == "pymupdf4llm"

    def test_supports_ocr_returns_false(self) -> None:
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        assert parser.supports_ocr() is False


class TestPyMuPDF4LLMParserParse:

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_parse_returns_documents_per_page(
        self, mock_fitz: MagicMock, mock_pymupdf4llm: MagicMock
    ) -> None:
        _setup_mock_fitz(mock_fitz, page_count=3)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([
            "# Page 1\n\nContent 1",
            "# Page 2\n\nContent 2",
            "# Page 3\n\nContent 3",
        ])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/test.pdf", "user-123")

        assert len(docs) == 3

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_parse_page_numbers_are_1_indexed(
        self, mock_fitz: MagicMock, mock_pymupdf4llm: MagicMock
    ) -> None:
        _setup_mock_fitz(mock_fitz, page_count=3)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([
            "Page 1 text", "Page 2 text", "Page 3 text",
        ])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/test.pdf", "user-123")

        assert docs[0].metadata["page"] == 1
        assert docs[1].metadata["page"] == 2
        assert docs[2].metadata["page"] == 3

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_parse_total_pages_matches_pdf(
        self, mock_fitz: MagicMock, mock_pymupdf4llm: MagicMock
    ) -> None:
        _setup_mock_fitz(mock_fitz, page_count=5)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([
            "p1", "p2", "p3", "p4", "p5",
        ])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/test.pdf", "user-123")

        for doc in docs:
            assert doc.metadata["total_pages"] == 5

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_parse_output_is_markdown_format(
        self, mock_fitz: MagicMock, mock_pymupdf4llm: MagicMock
    ) -> None:
        _setup_mock_fitz(mock_fitz, page_count=1)
        markdown_text = "# Heading\n\nParagraph text\n\n- item 1\n- item 2"
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([markdown_text])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/test.pdf", "user-123")

        assert docs[0].page_content == markdown_text

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_parse_metadata_has_parser_name(
        self, mock_fitz: MagicMock, mock_pymupdf4llm: MagicMock
    ) -> None:
        _setup_mock_fitz(mock_fitz, page_count=1)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks(["content"])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/test.pdf", "user-123")

        assert docs[0].metadata["parser"] == "pymupdf4llm"

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_parse_metadata_has_output_format(
        self, mock_fitz: MagicMock, mock_pymupdf4llm: MagicMock
    ) -> None:
        _setup_mock_fitz(mock_fitz, page_count=1)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks(["content"])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/test.pdf", "user-123")

        assert docs[0].metadata["output_format"] == "markdown"

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_parse_empty_pages_skipped(
        self, mock_fitz: MagicMock, mock_pymupdf4llm: MagicMock
    ) -> None:
        _setup_mock_fitz(mock_fitz, page_count=3)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([
            "# Page 1\n\nContent",
            "   \n\n   ",
            "# Page 3\n\nContent",
        ])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/test.pdf", "user-123")

        assert len(docs) == 2
        assert docs[0].metadata["page"] == 1
        assert docs[1].metadata["page"] == 3
        assert docs[0].metadata["total_pages"] == 3

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_parse_all_empty_pages_returns_empty(
        self, mock_fitz: MagicMock, mock_pymupdf4llm: MagicMock
    ) -> None:
        _setup_mock_fitz(mock_fitz, page_count=2)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([
            "   ", "   \n\n   ",
        ])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/test.pdf", "user-123")

        assert len(docs) == 0

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_parse_zero_page_pdf_returns_empty(
        self, mock_fitz: MagicMock, mock_pymupdf4llm: MagicMock
    ) -> None:
        _setup_mock_fitz(mock_fitz, page_count=0)
        mock_pymupdf4llm.to_markdown.return_value = []

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/empty.pdf", "user-123")

        assert len(docs) == 0

    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_parse_invalid_pdf_raises_exception(
        self, mock_fitz: MagicMock
    ) -> None:
        mock_fitz.open.side_effect = RuntimeError("Cannot open file")

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        with pytest.raises(RuntimeError):
            parser.parse("/path/to/invalid.pdf", "user-123")

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_parse_calls_to_markdown_with_page_chunks(
        self, mock_fitz: MagicMock, mock_pymupdf4llm: MagicMock
    ) -> None:
        _setup_mock_fitz(mock_fitz, page_count=1)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks(["content"])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        parser.parse("/path/to/test.pdf", "user-123")

        call_kwargs = mock_pymupdf4llm.to_markdown.call_args
        assert call_kwargs[1].get("page_chunks") is True
        assert call_kwargs[1].get("write_images") is False
        assert call_kwargs[1].get("show_progress") is False


class TestPyMuPDF4LLMParserParseBytes:

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_parse_bytes_returns_documents_per_page(
        self, mock_fitz: MagicMock, mock_pymupdf4llm: MagicMock
    ) -> None:
        _setup_mock_fitz(mock_fitz, page_count=2)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([
            "# From bytes page 1\n\ncontent",
            "# From bytes page 2\n\ncontent",
        ])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        docs = parser.parse_bytes(b"fake-pdf", "report.pdf", "user-123")

        assert len(docs) == 2
        assert docs[0].metadata["filename"] == "report.pdf"
        assert docs[0].metadata["user_id"] == "user-123"
        assert docs[0].metadata["parser"] == "pymupdf4llm"
        assert docs[0].metadata["page"] == 1
        assert docs[1].metadata["page"] == 2

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_parse_bytes_opens_with_stream(
        self, mock_fitz: MagicMock, mock_pymupdf4llm: MagicMock
    ) -> None:
        _setup_mock_fitz(mock_fitz, page_count=1)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks(["content"])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        pdf_bytes = b"fake-pdf-bytes"
        parser.parse_bytes(pdf_bytes, "test.pdf", "user-123")

        mock_fitz.open.assert_called_once()
        call_kwargs = mock_fitz.open.call_args
        assert call_kwargs[1].get("stream") == pdf_bytes
        assert call_kwargs[1].get("filetype") == "pdf"


class TestPyMuPDF4LLMParserSectionTitle:

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_section_title_extracted_from_h1(
        self, mock_fitz: MagicMock, mock_pymupdf4llm: MagicMock
    ) -> None:
        _setup_mock_fitz(mock_fitz, page_count=1)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([
            "# 대출한도 산출기준\n\n본문 내용...",
        ])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/test.pdf", "user-123")

        assert docs[0].metadata["section_title"] == "대출한도 산출기준"

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_section_title_extracted_from_h2(
        self, mock_fitz: MagicMock, mock_pymupdf4llm: MagicMock
    ) -> None:
        _setup_mock_fitz(mock_fitz, page_count=1)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([
            "## 2.1 심사 기준\n\n내용...",
        ])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/test.pdf", "user-123")

        assert docs[0].metadata["section_title"] == "2.1 심사 기준"

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_section_title_empty_when_no_heading(
        self, mock_fitz: MagicMock, mock_pymupdf4llm: MagicMock
    ) -> None:
        _setup_mock_fitz(mock_fitz, page_count=1)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([
            "일반 텍스트만 있는 페이지\n\n두 번째 문단",
        ])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/test.pdf", "user-123")

        assert docs[0].metadata["section_title"] == ""

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_section_title_per_page(
        self, mock_fitz: MagicMock, mock_pymupdf4llm: MagicMock
    ) -> None:
        _setup_mock_fitz(mock_fitz, page_count=3)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([
            "# 개요\n\n내용",
            "## 대출한도\n\n| A | B |\n|---|---|\n| 1 | 2 |",
            "본문만 있는 페이지",
        ])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/test.pdf", "user-123")

        assert docs[0].metadata["section_title"] == "개요"
        assert docs[1].metadata["section_title"] == "대출한도"
        assert docs[2].metadata["section_title"] == ""


class TestPyMuPDF4LLMParserHasTable:

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_has_table_true_when_table_present(
        self, mock_fitz: MagicMock, mock_pymupdf4llm: MagicMock
    ) -> None:
        _setup_mock_fitz(mock_fitz, page_count=1)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([
            "# 표 포함\n\n| 구분 | 한도 |\n|---|---|\n| A | 100 |\n",
        ])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/test.pdf", "user-123")

        assert docs[0].metadata["has_table"] is True

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_has_table_false_when_no_table(
        self, mock_fitz: MagicMock, mock_pymupdf4llm: MagicMock
    ) -> None:
        _setup_mock_fitz(mock_fitz, page_count=1)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([
            "# 제목\n\n일반 텍스트만 있는 페이지",
        ])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/test.pdf", "user-123")

        assert docs[0].metadata["has_table"] is False

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_has_table_true_even_when_tables_stripped(
        self, mock_fitz: MagicMock, mock_pymupdf4llm: MagicMock
    ) -> None:
        _setup_mock_fitz(mock_fitz, page_count=1)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([
            "# 제목\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n끝",
        ])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        config = ParserConfig(extract_tables=False)
        docs = parser.parse("/path/to/test.pdf", "user-123", config=config)

        assert docs[0].metadata["has_table"] is True
        assert "| A | B |" not in docs[0].page_content

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_has_table_per_page(
        self, mock_fitz: MagicMock, mock_pymupdf4llm: MagicMock
    ) -> None:
        _setup_mock_fitz(mock_fitz, page_count=2)
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([
            "# 텍스트만\n\n내용",
            "# 표 포함\n\n| X | Y |\n|---|---|\n| 1 | 2 |",
        ])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        docs = parser.parse("/path/to/test.pdf", "user-123")

        assert docs[0].metadata["has_table"] is False
        assert docs[1].metadata["has_table"] is True


class TestPyMuPDF4LLMParserTableExtraction:

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_extract_tables_true_includes_tables(
        self, mock_fitz: MagicMock, mock_pymupdf4llm: MagicMock
    ) -> None:
        _setup_mock_fitz(mock_fitz, page_count=1)
        md_with_table = "# Title\n\n| Col1 | Col2 |\n|---|---|\n| A | B |\n\nEnd"
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([md_with_table])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        config = ParserConfig(extract_tables=True)
        docs = parser.parse("/path/to/test.pdf", "user-123", config=config)

        assert "| Col1 | Col2 |" in docs[0].page_content

    @patch("src.infrastructure.parser.pymupdf4llm_parser.pymupdf4llm")
    @patch("src.infrastructure.parser.pymupdf4llm_parser.fitz")
    def test_extract_tables_false_strips_tables(
        self, mock_fitz: MagicMock, mock_pymupdf4llm: MagicMock
    ) -> None:
        _setup_mock_fitz(mock_fitz, page_count=1)
        md_with_table = "# Title\n\n| Col1 | Col2 |\n|---|---|\n| A | B |\n\nEnd"
        mock_pymupdf4llm.to_markdown.return_value = _make_page_chunks([md_with_table])

        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        parser = PyMuPDF4LLMParser()
        config = ParserConfig(extract_tables=False)
        docs = parser.parse("/path/to/test.pdf", "user-123", config=config)

        assert "| Col1 | Col2 |" not in docs[0].page_content
        assert "# Title" in docs[0].page_content
        assert "End" in docs[0].page_content


class TestExtractFirstHeading:

    def test_h1(self) -> None:
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        assert PyMuPDF4LLMParser._extract_first_heading("# Hello\n\nbody") == "Hello"

    def test_h2(self) -> None:
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        assert PyMuPDF4LLMParser._extract_first_heading("## Sub Title\n\n") == "Sub Title"

    def test_h3(self) -> None:
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        assert PyMuPDF4LLMParser._extract_first_heading("### Deep\n") == "Deep"

    def test_no_heading(self) -> None:
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        assert PyMuPDF4LLMParser._extract_first_heading("no heading here") == ""

    def test_empty_string(self) -> None:
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        assert PyMuPDF4LLMParser._extract_first_heading("") == ""

    def test_first_heading_only(self) -> None:
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        result = PyMuPDF4LLMParser._extract_first_heading("# First\n\n## Second\n")
        assert result == "First"

    def test_heading_with_leading_text(self) -> None:
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        result = PyMuPDF4LLMParser._extract_first_heading("text\n\n# Title\n")
        assert result == "Title"


class TestDetectTable:

    def test_standard_table(self) -> None:
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        assert PyMuPDF4LLMParser._detect_table(md) is True

    def test_no_table(self) -> None:
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        assert PyMuPDF4LLMParser._detect_table("just text") is False

    def test_pipe_without_separator(self) -> None:
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        md = "| A | B |\n| 1 | 2 |"
        assert PyMuPDF4LLMParser._detect_table(md) is False

    def test_empty_string(self) -> None:
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        assert PyMuPDF4LLMParser._detect_table("") is False

    def test_table_embedded_in_text(self) -> None:
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser
        md = "Before\n\n| X | Y |\n|---|---|\n| a | b |\n\nAfter"
        assert PyMuPDF4LLMParser._detect_table(md) is True


class TestStripMarkdownTables:

    def test_removes_simple_table(self) -> None:
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        text = "Before\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\nAfter"
        result = PyMuPDF4LLMParser._strip_markdown_tables(text)

        assert "| A | B |" not in result
        assert "Before" in result
        assert "After" in result

    def test_preserves_non_table_content(self) -> None:
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        text = "# Heading\n\nParagraph text\n\n- list item"
        result = PyMuPDF4LLMParser._strip_markdown_tables(text)

        assert result == text

    def test_removes_multi_row_table(self) -> None:
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        text = "Start\n| H1 | H2 | H3 |\n|---|---|---|\n| a | b | c |\n| d | e | f |\n| g | h | i |\nEnd"
        result = PyMuPDF4LLMParser._strip_markdown_tables(text)

        assert "|" not in result
        assert "Start" in result
        assert "End" in result

    def test_handles_empty_string(self) -> None:
        from src.infrastructure.parser.pymupdf4llm_parser import PyMuPDF4LLMParser

        result = PyMuPDF4LLMParser._strip_markdown_tables("")
        assert result == ""
