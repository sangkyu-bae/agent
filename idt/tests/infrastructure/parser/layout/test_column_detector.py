"""Tests for ColumnDetector."""
import pytest

from src.domain.parser.document_element import BoundingBox, DocumentElement
from src.infrastructure.parser.layout.column_detector import (
    ColumnDetector,
    LayoutType,
)

PAGE_WIDTH = 595.0


def _elem(x0: float, x1: float, text: str = "t") -> DocumentElement:
    return DocumentElement(
        page_no=1,
        text=text,
        bbox=BoundingBox(x0=x0, y0=100.0, x1=x1, y1=120.0),
        block_type="paragraph",
    )


def _left_elem(text: str = "left") -> DocumentElement:
    return _elem(20.0, 260.0, text)


def _right_elem(text: str = "right") -> DocumentElement:
    return _elem(320.0, 575.0, text)


def _full_width_elem(text: str = "full") -> DocumentElement:
    return _elem(20.0, 575.0, text)


class TestColumnDetector:

    def test_empty_elements_returns_single(self) -> None:
        detector = ColumnDetector()
        assert detector.detect([], PAGE_WIDTH) == LayoutType.SINGLE

    def test_single_column_layout(self) -> None:
        elements = [_full_width_elem("본문") for _ in range(5)]
        detector = ColumnDetector()
        assert detector.detect(elements, PAGE_WIDTH) == LayoutType.SINGLE

    def test_double_column_layout(self) -> None:
        elements = [
            _left_elem("좌1"), _left_elem("좌2"), _left_elem("좌3"),
            _right_elem("우1"), _right_elem("우2"), _right_elem("우3"),
        ]
        detector = ColumnDetector()
        assert detector.detect(elements, PAGE_WIDTH) == LayoutType.DOUBLE

    def test_mixed_layout(self) -> None:
        elements = [
            _full_width_elem("제목"),
            _left_elem("좌1"), _left_elem("좌2"),
            _right_elem("우1"), _right_elem("우2"),
        ]
        detector = ColumnDetector()
        assert detector.detect(elements, PAGE_WIDTH) == LayoutType.MIXED

    def test_mostly_left_returns_single(self) -> None:
        elements = [_left_elem() for _ in range(8)] + [_right_elem()]
        detector = ColumnDetector()
        result = detector.detect(elements, PAGE_WIDTH)
        assert result == LayoutType.SINGLE

    def test_center_elements_only(self) -> None:
        elements = [_elem(250.0, 345.0) for _ in range(5)]
        detector = ColumnDetector()
        assert detector.detect(elements, PAGE_WIDTH) == LayoutType.SINGLE


class TestColumnDetectorSplit:

    def test_split_two_column(self) -> None:
        elements = [
            _left_elem("L"), _right_elem("R"), _full_width_elem("F"),
        ]
        detector = ColumnDetector()
        left, right, full = detector.split_columns(elements, PAGE_WIDTH)

        assert len(left) == 1
        assert len(right) == 1
        assert len(full) == 1
        assert left[0].text == "L"
        assert right[0].text == "R"
        assert full[0].text == "F"

    def test_split_empty(self) -> None:
        detector = ColumnDetector()
        left, right, full = detector.split_columns([], PAGE_WIDTH)
        assert left == [] and right == [] and full == []
