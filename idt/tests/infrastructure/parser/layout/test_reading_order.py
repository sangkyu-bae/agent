"""Tests for ReadingOrderReconstructor."""
import pytest

from src.domain.parser.document_element import BoundingBox, DocumentElement
from src.infrastructure.parser.layout.column_detector import LayoutType
from src.infrastructure.parser.layout.reading_order import (
    ReadingOrderReconstructor,
)

PAGE_WIDTH = 595.0


def _elem(
    text: str, x0: float, y0: float, x1: float, y1: float
) -> DocumentElement:
    return DocumentElement(
        page_no=1,
        text=text,
        bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1),
        block_type="paragraph",
    )


class TestReadingOrderSingle:

    def test_empty_returns_empty(self) -> None:
        r = ReadingOrderReconstructor()
        assert r.reconstruct([], LayoutType.SINGLE, PAGE_WIDTH) == []

    def test_single_column_y_then_x(self) -> None:
        elems = [
            _elem("C", 10, 100, 200, 120),
            _elem("A", 10, 10, 200, 30),
            _elem("B", 10, 50, 200, 70),
        ]
        r = ReadingOrderReconstructor()
        ordered = r.reconstruct(elems, LayoutType.SINGLE, PAGE_WIDTH)

        assert [e.text for e in ordered] == ["A", "B", "C"]

    def test_reading_order_assigned(self) -> None:
        elems = [
            _elem("B", 10, 50, 200, 70),
            _elem("A", 10, 10, 200, 30),
        ]
        r = ReadingOrderReconstructor()
        ordered = r.reconstruct(elems, LayoutType.SINGLE, PAGE_WIDTH)

        assert ordered[0].reading_order == 0
        assert ordered[1].reading_order == 1


class TestReadingOrderDouble:

    def test_left_then_right(self) -> None:
        elems = [
            _elem("R1", 320, 10, 575, 30),
            _elem("L1", 20, 10, 260, 30),
            _elem("R2", 320, 50, 575, 70),
            _elem("L2", 20, 50, 260, 70),
        ]
        r = ReadingOrderReconstructor()
        ordered = r.reconstruct(elems, LayoutType.DOUBLE, PAGE_WIDTH)

        texts = [e.text for e in ordered]
        assert texts.index("L1") < texts.index("R1")
        assert texts.index("L2") < texts.index("R2")

    def test_full_width_interleaved(self) -> None:
        elems = [
            _elem("L1", 20, 10, 260, 30),
            _elem("TITLE", 20, 40, 575, 60),  # full width
            _elem("R1", 320, 70, 575, 90),
        ]
        r = ReadingOrderReconstructor()
        ordered = r.reconstruct(elems, LayoutType.DOUBLE, PAGE_WIDTH)

        texts = [e.text for e in ordered]
        assert texts[0] == "L1"
        assert texts[1] == "TITLE"
        assert texts[2] == "R1"


class TestReadingOrderMixed:

    def test_zones_separated_by_full_width(self) -> None:
        elems = [
            _elem("L1", 20, 10, 260, 30),
            _elem("R1", 320, 10, 575, 30),
            _elem("FULL", 20, 50, 575, 70),  # full width separator
            _elem("L2", 20, 80, 260, 100),
            _elem("R2", 320, 80, 575, 100),
        ]
        r = ReadingOrderReconstructor()
        ordered = r.reconstruct(elems, LayoutType.MIXED, PAGE_WIDTH)

        texts = [e.text for e in ordered]
        assert texts.index("L1") < texts.index("FULL")
        assert texts.index("R1") < texts.index("FULL")
        assert texts.index("FULL") < texts.index("L2")
        assert texts.index("FULL") < texts.index("R2")
