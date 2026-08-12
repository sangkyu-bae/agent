"""document_generator 도메인 정책 테스트 (Design §4-2)."""
import pytest

from src.domain.document_generator.exceptions import InvalidGenerationTypeError
from src.domain.document_generator.policies import (
    DEFAULT_MAX_SECTIONS,
    GenerationTypePolicy,
    SectionCoveragePolicy,
    SectionPolicy,
)
from src.domain.document_generator.schemas import DocumentSection


def _sections(*titles: str) -> list[DocumentSection]:
    return [DocumentSection(title=t) for t in titles]


class TestSectionPolicy:
    def test_valid_sections_pass(self):
        SectionPolicy.validate(_sections("개요", "시장 현황", "결론"))

    def test_empty_sections_rejected(self):
        with pytest.raises(InvalidGenerationTypeError):
            SectionPolicy.validate([])

    def test_over_max_sections_rejected(self):
        sections = _sections(*[f"섹션{i}" for i in range(DEFAULT_MAX_SECTIONS + 1)])
        with pytest.raises(InvalidGenerationTypeError):
            SectionPolicy.validate(sections)

    def test_custom_max_sections(self):
        with pytest.raises(InvalidGenerationTypeError):
            SectionPolicy.validate(_sections("a", "b", "c"), max_sections=2)

    def test_empty_title_rejected(self):
        with pytest.raises(InvalidGenerationTypeError):
            SectionPolicy.validate([DocumentSection(title="  ")])

    def test_title_too_long_rejected(self):
        with pytest.raises(InvalidGenerationTypeError):
            SectionPolicy.validate([DocumentSection(title="가" * 101)])

    def test_duplicate_title_rejected(self):
        with pytest.raises(InvalidGenerationTypeError):
            SectionPolicy.validate(_sections("개요", "개요"))

    def test_guidance_too_long_rejected(self):
        with pytest.raises(InvalidGenerationTypeError):
            SectionPolicy.validate(
                [DocumentSection(title="개요", guidance="가" * 501)]
            )


class TestGenerationTypePolicy:
    def test_valid_passes(self):
        GenerationTypePolicy.validate("시장조사 보고서", "설명", "docx")

    def test_empty_name_rejected(self):
        with pytest.raises(InvalidGenerationTypeError):
            GenerationTypePolicy.validate("  ", "", "docx")

    def test_name_too_long_rejected(self):
        with pytest.raises(InvalidGenerationTypeError):
            GenerationTypePolicy.validate("가" * 101, "", "docx")

    def test_description_too_long_rejected(self):
        with pytest.raises(InvalidGenerationTypeError):
            GenerationTypePolicy.validate("보고서", "가" * 501, "docx")

    @pytest.mark.parametrize("fmt", ["pdf", "docx"])
    def test_allowed_formats(self, fmt):
        GenerationTypePolicy.validate("보고서", "", fmt)

    @pytest.mark.parametrize("fmt", ["", "hwp", "PDF", "html"])
    def test_invalid_format_rejected(self, fmt):
        with pytest.raises(InvalidGenerationTypeError):
            GenerationTypePolicy.validate("보고서", "", fmt)


class TestSectionCoveragePolicy:
    def test_all_titles_present_returns_empty(self):
        html = "<h1>보고서</h1><h2>개요</h2><p>...</p><h2>시장 현황</h2>"
        missing = SectionCoveragePolicy.missing_titles(
            html, _sections("개요", "시장 현황")
        )
        assert missing == []

    def test_missing_title_reported(self):
        html = "<h1>보고서</h1><h2>개요</h2>"
        missing = SectionCoveragePolicy.missing_titles(
            html, _sections("개요", "경쟁 분석")
        )
        assert missing == ["경쟁 분석"]

    def test_heading_levels_h1_to_h3_accepted(self):
        html = "<h1>개요</h1><h3>결론</h3>"
        assert SectionCoveragePolicy.missing_titles(
            html, _sections("개요", "결론")
        ) == []

    def test_whitespace_normalized_match(self):
        html = "<h2>시장   현황</h2>"
        assert SectionCoveragePolicy.missing_titles(
            html, _sections("시장 현황")
        ) == []

    def test_heading_with_attributes_and_partial_match(self):
        html = '<h2 class="sec">1. 개요 및 배경</h2>'
        assert SectionCoveragePolicy.missing_titles(html, _sections("개요 및 배경")) == []

    def test_body_text_does_not_count_as_heading(self):
        html = "<p>개요</p>"
        assert SectionCoveragePolicy.missing_titles(html, _sections("개요")) == ["개요"]
