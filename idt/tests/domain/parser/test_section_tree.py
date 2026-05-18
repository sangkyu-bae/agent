"""Tests for SectionNode value object."""
import pytest

from src.domain.parser.document_element import BoundingBox, DocumentElement
from src.domain.parser.section_tree import SectionNode


def _elem(text: str, block_type: str = "paragraph") -> DocumentElement:
    return DocumentElement(
        page_no=1,
        text=text,
        bbox=BoundingBox(0.0, 0.0, 100.0, 20.0),
        block_type=block_type,
    )


class TestSectionNode:

    def test_create_basic_node(self) -> None:
        node = SectionNode(
            title="제1조",
            level=1,
            elements=[_elem("본문 내용")],
            children=[],
            page_range=(1, 1),
        )
        assert node.title == "제1조"
        assert node.level == 1
        assert node.page_range == (1, 1)

    def test_text_content(self) -> None:
        node = SectionNode(
            title="섹션",
            level=1,
            elements=[_elem("첫째"), _elem("둘째"), _elem("셋째")],
            children=[],
            page_range=(1, 1),
        )
        assert node.text_content == "첫째\n둘째\n셋째"

    def test_text_content_empty(self) -> None:
        node = SectionNode(
            title="빈 섹션", level=1, elements=[], children=[], page_range=(1, 1),
        )
        assert node.text_content == ""

    def test_has_table_true(self) -> None:
        node = SectionNode(
            title="표 포함",
            level=1,
            elements=[_elem("텍스트"), _elem("| A | B |", "table")],
            children=[],
            page_range=(1, 1),
        )
        assert node.has_table is True

    def test_has_table_false(self) -> None:
        node = SectionNode(
            title="표 없음",
            level=1,
            elements=[_elem("일반 텍스트")],
            children=[],
            page_range=(1, 1),
        )
        assert node.has_table is False

    def test_has_table_row_type(self) -> None:
        node = SectionNode(
            title="표행",
            level=1,
            elements=[_elem("| 1 | 2 |", "table_row")],
            children=[],
            page_range=(1, 1),
        )
        assert node.has_table is True

    def test_flatten_no_children(self) -> None:
        node = SectionNode(
            title="루트", level=1, elements=[], children=[], page_range=(1, 1),
        )
        flat = node.flatten()
        assert len(flat) == 1
        assert flat[0].title == "루트"

    def test_flatten_with_children(self) -> None:
        child1 = SectionNode(
            title="1.1", level=2, elements=[], children=[], page_range=(1, 1),
        )
        child2 = SectionNode(
            title="1.2", level=2, elements=[], children=[], page_range=(2, 2),
        )
        root = SectionNode(
            title="제1장", level=1, elements=[],
            children=[child1, child2], page_range=(1, 2),
        )
        flat = root.flatten()
        assert len(flat) == 3
        assert [n.title for n in flat] == ["제1장", "1.1", "1.2"]

    def test_flatten_nested_deeply(self) -> None:
        leaf = SectionNode(
            title="깊은노드", level=3, elements=[], children=[], page_range=(1, 1),
        )
        mid = SectionNode(
            title="중간", level=2, elements=[], children=[leaf], page_range=(1, 1),
        )
        root = SectionNode(
            title="루트", level=1, elements=[], children=[mid], page_range=(1, 1),
        )
        flat = root.flatten()
        assert len(flat) == 3
        assert flat[2].title == "깊은노드"
