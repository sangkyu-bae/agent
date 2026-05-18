"""Tests for BoundingBox and DocumentElement value objects."""
import pytest
from dataclasses import replace

from src.domain.parser.document_element import BoundingBox, DocumentElement


class TestBoundingBox:
    """Tests for BoundingBox value object."""

    def test_create_valid_bbox(self) -> None:
        bbox = BoundingBox(x0=10.0, y0=20.0, x1=100.0, y1=200.0)
        assert bbox.x0 == 10.0
        assert bbox.y0 == 20.0
        assert bbox.x1 == 100.0
        assert bbox.y1 == 200.0

    def test_x1_less_than_x0_raises_error(self) -> None:
        with pytest.raises(ValueError, match="x1 must be >= x0"):
            BoundingBox(x0=100.0, y0=0.0, x1=50.0, y1=100.0)

    def test_y1_less_than_y0_raises_error(self) -> None:
        with pytest.raises(ValueError, match="y1 must be >= y0"):
            BoundingBox(x0=0.0, y0=200.0, x1=100.0, y1=100.0)

    def test_zero_size_bbox_is_valid(self) -> None:
        bbox = BoundingBox(x0=50.0, y0=50.0, x1=50.0, y1=50.0)
        assert bbox.width == 0.0
        assert bbox.height == 0.0

    def test_width_property(self) -> None:
        bbox = BoundingBox(x0=10.0, y0=0.0, x1=110.0, y1=50.0)
        assert bbox.width == 100.0

    def test_height_property(self) -> None:
        bbox = BoundingBox(x0=0.0, y0=10.0, x1=50.0, y1=210.0)
        assert bbox.height == 200.0

    def test_center_x_property(self) -> None:
        bbox = BoundingBox(x0=0.0, y0=0.0, x1=100.0, y1=50.0)
        assert bbox.center_x == 50.0

    def test_center_y_property(self) -> None:
        bbox = BoundingBox(x0=0.0, y0=0.0, x1=100.0, y1=200.0)
        assert bbox.center_y == 100.0

    def test_area_property(self) -> None:
        bbox = BoundingBox(x0=0.0, y0=0.0, x1=10.0, y1=20.0)
        assert bbox.area == 200.0

    def test_is_within_top_ratio_true(self) -> None:
        bbox = BoundingBox(x0=0.0, y0=0.0, x1=100.0, y1=80.0)
        assert bbox.is_within_top_ratio(842.0, 0.10) is True

    def test_is_within_top_ratio_boundary(self) -> None:
        bbox = BoundingBox(x0=0.0, y0=0.0, x1=100.0, y1=84.2)
        assert bbox.is_within_top_ratio(842.0, 0.10) is True

    def test_is_within_top_ratio_false(self) -> None:
        bbox = BoundingBox(x0=0.0, y0=0.0, x1=100.0, y1=100.0)
        assert bbox.is_within_top_ratio(842.0, 0.10) is False

    def test_is_within_bottom_ratio_true(self) -> None:
        bbox = BoundingBox(x0=0.0, y0=760.0, x1=100.0, y1=842.0)
        assert bbox.is_within_bottom_ratio(842.0, 0.90) is True

    def test_is_within_bottom_ratio_false(self) -> None:
        bbox = BoundingBox(x0=0.0, y0=400.0, x1=100.0, y1=500.0)
        assert bbox.is_within_bottom_ratio(842.0, 0.90) is False

    def test_is_immutable(self) -> None:
        bbox = BoundingBox(x0=0.0, y0=0.0, x1=100.0, y1=100.0)
        with pytest.raises(AttributeError):
            bbox.x0 = 50.0

    def test_equality(self) -> None:
        bbox1 = BoundingBox(x0=0.0, y0=0.0, x1=100.0, y1=100.0)
        bbox2 = BoundingBox(x0=0.0, y0=0.0, x1=100.0, y1=100.0)
        assert bbox1 == bbox2

    def test_inequality(self) -> None:
        bbox1 = BoundingBox(x0=0.0, y0=0.0, x1=100.0, y1=100.0)
        bbox2 = BoundingBox(x0=0.0, y0=0.0, x1=200.0, y1=100.0)
        assert bbox1 != bbox2


class TestDocumentElement:
    """Tests for DocumentElement value object."""

    def _make_bbox(self) -> BoundingBox:
        return BoundingBox(x0=0.0, y0=0.0, x1=100.0, y1=20.0)

    def test_create_valid_element(self) -> None:
        elem = DocumentElement(
            page_no=1,
            text="테스트 텍스트",
            bbox=self._make_bbox(),
            block_type="paragraph",
        )
        assert elem.page_no == 1
        assert elem.text == "테스트 텍스트"
        assert elem.block_type == "paragraph"

    def test_default_values(self) -> None:
        elem = DocumentElement(
            page_no=1,
            text="text",
            bbox=self._make_bbox(),
            block_type="paragraph",
        )
        assert elem.section_title == ""
        assert elem.reading_order == 0
        assert elem.font_size == 0.0
        assert elem.is_bold is False
        assert elem.confidence == 1.0

    def test_page_no_zero_raises_error(self) -> None:
        with pytest.raises(ValueError, match="page_no must be >= 1"):
            DocumentElement(
                page_no=0,
                text="text",
                bbox=self._make_bbox(),
                block_type="paragraph",
            )

    def test_page_no_negative_raises_error(self) -> None:
        with pytest.raises(ValueError, match="page_no must be >= 1"):
            DocumentElement(
                page_no=-1,
                text="text",
                bbox=self._make_bbox(),
                block_type="paragraph",
            )

    def test_invalid_bbox_type_raises_error(self) -> None:
        with pytest.raises(TypeError, match="bbox must be a BoundingBox"):
            DocumentElement(
                page_no=1,
                text="text",
                bbox=(0, 0, 100, 100),  # type: ignore
                block_type="paragraph",
            )

    def test_is_immutable(self) -> None:
        elem = DocumentElement(
            page_no=1,
            text="text",
            bbox=self._make_bbox(),
            block_type="paragraph",
        )
        with pytest.raises(AttributeError):
            elem.text = "new text"

    def test_replace_creates_new_instance(self) -> None:
        elem = DocumentElement(
            page_no=1,
            text="text",
            bbox=self._make_bbox(),
            block_type="paragraph",
        )
        new_elem = replace(elem, section_title="제1조")
        assert new_elem.section_title == "제1조"
        assert elem.section_title == ""

    def test_various_block_types(self) -> None:
        bbox = self._make_bbox()
        for block_type in ["title", "heading", "paragraph", "table", "footer"]:
            elem = DocumentElement(
                page_no=1, text="t", bbox=bbox, block_type=block_type,
            )
            assert elem.block_type == block_type

    def test_custom_font_and_bold(self) -> None:
        elem = DocumentElement(
            page_no=1,
            text="굵은 제목",
            bbox=self._make_bbox(),
            block_type="heading",
            font_size=16.0,
            is_bold=True,
        )
        assert elem.font_size == 16.0
        assert elem.is_bold is True
