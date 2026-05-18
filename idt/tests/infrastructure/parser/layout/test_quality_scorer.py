"""Tests for QualityScorer."""
from unittest.mock import MagicMock
import pytest

from src.domain.parser.document_element import BoundingBox, DocumentElement
from src.infrastructure.parser.layout.quality_scorer import QualityScorer

PAGE_HEIGHT = 842.0


def _elem(
    text: str,
    y0: float = 100.0,
    block_type: str = "paragraph",
) -> DocumentElement:
    return DocumentElement(
        page_no=1,
        text=text,
        bbox=BoundingBox(10.0, y0, 200.0, y0 + 20.0),
        block_type=block_type,
    )


class TestQualityScorerPage:

    def test_empty_page_score_zero(self) -> None:
        scorer = QualityScorer()
        result = scorer.score_page([], PAGE_HEIGHT)

        assert result.score == 0.0
        assert "empty_page" in result.issues

    def test_normal_page_high_score(self) -> None:
        elements = [_elem("이것은 정상적인 문서 텍스트입니다. " * 20, y0=i * 30.0) for i in range(5)]
        scorer = QualityScorer()
        result = scorer.score_page(elements, PAGE_HEIGHT)

        assert result.score >= 0.8

    def test_low_text_extraction(self) -> None:
        elements = [_elem("짧은", y0=100.0)]
        scorer = QualityScorer()
        result = scorer.score_page(elements, PAGE_HEIGHT)

        assert "low_text_extraction" in result.issues

    def test_fragmented_text(self) -> None:
        elements = [_elem("a b c d e f g h i j k l m n", y0=i * 30.0) for i in range(5)]
        scorer = QualityScorer()
        result = scorer.score_page(elements, PAGE_HEIGHT)

        assert "fragmented_text" in result.issues

    def test_reading_order_broken(self) -> None:
        elements = [
            _elem("세번째", y0=300.0),
            _elem("첫번째", y0=100.0),
            _elem("두번째", y0=200.0),
        ]
        scorer = QualityScorer()
        result = scorer.score_page(elements, PAGE_HEIGHT)

        assert "reading_order_broken" in result.issues

    def test_table_not_detected(self) -> None:
        elements = [_elem("| A | B |\n| 1 | 2 |", y0=100.0)]
        scorer = QualityScorer()
        result = scorer.score_page(elements, PAGE_HEIGHT)

        assert "table_not_detected" in result.issues

    def test_table_properly_detected(self) -> None:
        elements = [
            _elem("| A | B |", y0=100.0, block_type="table"),
        ]
        scorer = QualityScorer()
        result = scorer.score_page(elements, PAGE_HEIGHT)

        assert "table_not_detected" not in result.issues

    def test_text_char_count(self) -> None:
        elements = [_elem("hello world", y0=100.0)]
        scorer = QualityScorer()
        result = scorer.score_page(elements, PAGE_HEIGHT)

        assert result.text_char_count == 11

    def test_order_consistency_perfect(self) -> None:
        elements = [_elem("a", y0=i * 30.0) for i in range(5)]
        scorer = QualityScorer()
        result = scorer.score_page(elements, PAGE_HEIGHT)

        assert result.order_consistency == 1.0


class TestQualityScorerDocuments:

    def _mock_doc(self, content: str) -> MagicMock:
        doc = MagicMock()
        doc.page_content = content
        return doc

    def test_empty_documents(self) -> None:
        scorer = QualityScorer()
        result = scorer.score_documents([])

        assert result.score == 0.0
        assert "no_documents" in result.issues

    def test_normal_documents(self) -> None:
        docs = [self._mock_doc("이것은 정상적인 문서입니다. " * 20)]
        scorer = QualityScorer()
        result = scorer.score_documents(docs)

        assert result.score >= 0.8

    def test_low_text_documents(self) -> None:
        docs = [self._mock_doc("짧은")]
        scorer = QualityScorer()
        result = scorer.score_documents(docs)

        assert "low_text_extraction" in result.issues
