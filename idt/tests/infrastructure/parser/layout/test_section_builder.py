"""Tests for SectionBuilder."""
import pytest

from src.domain.parser.document_element import BoundingBox, DocumentElement
from src.infrastructure.parser.layout.section_builder import SectionBuilder


def _elem(
    text: str,
    font_size: float = 10.0,
    is_bold: bool = False,
    page_no: int = 1,
) -> DocumentElement:
    return DocumentElement(
        page_no=page_no,
        text=text,
        bbox=BoundingBox(10.0, 0.0, 200.0, 20.0),
        block_type="paragraph",
        font_size=font_size,
        is_bold=is_bold,
    )


class TestSectionBuilder:

    def test_empty_input(self) -> None:
        builder = SectionBuilder()
        assert builder.build([]) == []

    def test_no_headings_single_section(self) -> None:
        elements = [_elem("본문1"), _elem("본문2"), _elem("본문3")]
        builder = SectionBuilder()
        sections = builder.build(elements)

        assert len(sections) == 1
        assert sections[0].title == ""
        assert len(sections[0].elements) == 3

    def test_single_heading_creates_section(self) -> None:
        elements = [
            _elem("제1조 목적", font_size=16.0, is_bold=True),
            _elem("이 규정은 목적을 정한다."),
            _elem("세부 내용은 다음과 같다."),
        ]
        builder = SectionBuilder()
        sections = builder.build(elements)

        assert len(sections) == 1
        assert sections[0].title == "제1조 목적"
        assert len(sections[0].elements) == 3

    def test_multiple_headings(self) -> None:
        elements = [
            _elem("제1조", font_size=16.0, is_bold=True),
            _elem("본문1"),
            _elem("제2조", font_size=16.0, is_bold=True),
            _elem("본문2"),
        ]
        builder = SectionBuilder()
        sections = builder.build(elements)

        assert len(sections) == 2
        assert sections[0].title == "제1조"
        assert sections[1].title == "제2조"

    def test_body_before_first_heading(self) -> None:
        elements = [
            _elem("서문 내용"),
            _elem("제1조", font_size=16.0, is_bold=True),
            _elem("본문"),
        ]
        builder = SectionBuilder()
        sections = builder.build(elements)

        assert len(sections) == 2
        assert sections[0].title == ""
        assert sections[0].elements[0].text == "서문 내용"
        assert sections[1].title == "제1조"

    def test_page_range(self) -> None:
        elements = [
            _elem("제목", font_size=16.0, is_bold=True, page_no=1),
            _elem("본문1", page_no=1),
            _elem("본문2", page_no=2),
            _elem("본문3", page_no=3),
        ]
        builder = SectionBuilder()
        sections = builder.build(elements)

        assert sections[0].page_range == (1, 3)

    def test_heading_detection_by_size_ratio(self) -> None:
        elements = [
            _elem("작은 텍스트", font_size=10.0),
            _elem("큰 제목", font_size=14.0, is_bold=True),
            _elem("본문", font_size=10.0),
        ]
        builder = SectionBuilder()
        sections = builder.build(elements)

        has_heading = any(s.title == "큰 제목" for s in sections)
        assert has_heading

    def test_bold_required_at_exact_threshold(self) -> None:
        elements = [
            _elem("text1", font_size=10.0),
            _elem("text2", font_size=10.0),
            _elem("heading", font_size=12.0, is_bold=False),
        ]
        builder = SectionBuilder()
        sections = builder.build(elements)
        # 12.0 == 10.0 * 1.2 exact threshold, not > threshold, not bold → not heading
        assert len(sections) == 1


class TestSectionBuilderAssignTitles:

    def test_assign_section_titles(self) -> None:
        elements = [
            _elem("제1조", font_size=16.0, is_bold=True),
            _elem("본문1"),
            _elem("본문2"),
        ]
        builder = SectionBuilder()
        titled = builder.assign_section_titles(elements)

        assert all(e.section_title == "제1조" for e in titled)

    def test_different_sections_get_different_titles(self) -> None:
        elements = [
            _elem("섹션A", font_size=16.0, is_bold=True),
            _elem("본문A"),
            _elem("섹션B", font_size=16.0, is_bold=True),
            _elem("본문B"),
        ]
        builder = SectionBuilder()
        titled = builder.assign_section_titles(elements)

        assert titled[0].section_title == "섹션A"
        assert titled[1].section_title == "섹션A"
        assert titled[2].section_title == "섹션B"
        assert titled[3].section_title == "섹션B"

    def test_empty_input(self) -> None:
        builder = SectionBuilder()
        assert builder.assign_section_titles([]) == []
