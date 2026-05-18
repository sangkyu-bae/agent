"""Tests for LayoutAnalyzer (integration)."""
from unittest.mock import MagicMock, PropertyMock
import pytest

from src.infrastructure.parser.layout.layout_analyzer import LayoutAnalyzer


def _make_page_dict(lines: list[dict]) -> dict:
    return {
        "blocks": [
            {"type": 0, "lines": lines},
        ]
    }


def _line(text: str, bbox: tuple, font_size: float = 10.0) -> dict:
    return {
        "bbox": bbox,
        "spans": [{"text": text, "size": font_size, "font": "Arial"}],
    }


def _mock_pdf(pages_data: list[dict]) -> MagicMock:
    pdf = MagicMock()
    pdf.page_count = len(pages_data)

    mock_pages = []
    for data in pages_data:
        page = MagicMock()
        page.get_text.return_value = data
        page.find_tables.return_value = []
        rect = MagicMock()
        rect.height = 842.0
        rect.width = 595.0
        page.rect = rect
        mock_pages.append(page)

    pdf.__getitem__ = lambda self, idx: mock_pages[idx]
    return pdf


class TestLayoutAnalyzer:

    def test_single_page_basic(self) -> None:
        page_data = _make_page_dict([
            _line("제목입니다", (10, 10, 300, 30), font_size=16.0),
            _line("본문 텍스트가 여기에 들어갑니다. " * 10, (10, 50, 500, 70)),
            _line("추가 본문 내용입니다. " * 10, (10, 80, 500, 100)),
        ])
        pdf = _mock_pdf([page_data])
        analyzer = LayoutAnalyzer()
        docs, quality = analyzer.analyze(pdf, "test.pdf", "user1")

        assert len(docs) == 1
        assert "제목입니다" in docs[0].page_content
        assert docs[0].metadata["parser"] == "pymupdf_layout"
        assert docs[0].metadata["page"] == 1
        assert quality.score > 0

    def test_multi_page(self) -> None:
        page1 = _make_page_dict([
            _line("페이지 1 내용입니다. " * 15, (10, 50, 500, 70)),
        ])
        page2 = _make_page_dict([
            _line("페이지 2 내용입니다. " * 15, (10, 50, 500, 70)),
        ])
        pdf = _mock_pdf([page1, page2])
        analyzer = LayoutAnalyzer()
        docs, quality = analyzer.analyze(pdf, "multi.pdf", "user1")

        assert len(docs) == 2
        assert docs[0].metadata["page"] == 1
        assert docs[1].metadata["page"] == 2
        assert docs[0].metadata["total_pages"] == 2

    def test_empty_page_skipped(self) -> None:
        empty_page = {"blocks": []}
        content_page = _make_page_dict([
            _line("유효한 내용입니다. " * 15, (10, 50, 500, 70)),
        ])
        pdf = _mock_pdf([empty_page, content_page])
        analyzer = LayoutAnalyzer()
        docs, quality = analyzer.analyze(pdf, "test.pdf", "user1")

        assert len(docs) == 1
        assert docs[0].metadata["page"] == 2

    def test_quality_score_populated(self) -> None:
        page_data = _make_page_dict([
            _line("충분한 텍스트가 포함된 문서입니다. " * 20, (10, 50, 500, 70)),
        ])
        pdf = _mock_pdf([page_data])
        analyzer = LayoutAnalyzer()
        docs, quality = analyzer.analyze(pdf, "test.pdf", "user1")

        assert quality.text_char_count > 0
        assert 0.0 <= quality.score <= 1.0

    def test_metadata_includes_layout_type(self) -> None:
        page_data = _make_page_dict([
            _line("전체 너비 텍스트. " * 20, (10, 50, 580, 70)),
        ])
        pdf = _mock_pdf([page_data])
        analyzer = LayoutAnalyzer()
        docs, _ = analyzer.analyze(pdf, "test.pdf", "user1")

        assert "layout_type" in docs[0].metadata

    def test_no_pages_returns_empty(self) -> None:
        pdf = MagicMock()
        pdf.page_count = 0
        analyzer = LayoutAnalyzer()
        docs, quality = analyzer.analyze(pdf, "empty.pdf", "user1")

        assert docs == []
        assert quality.score == 0.0
