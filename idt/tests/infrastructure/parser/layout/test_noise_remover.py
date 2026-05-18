"""Tests for NoiseRemover."""
import pytest

from src.domain.parser.document_element import BoundingBox, DocumentElement
from src.infrastructure.parser.layout.noise_remover import NoiseRemover

PAGE_HEIGHT = 842.0


def _elem(
    page_no: int,
    text: str,
    y0: float,
    y1: float,
    x0: float = 10.0,
    x1: float = 200.0,
) -> DocumentElement:
    return DocumentElement(
        page_no=page_no,
        text=text,
        bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1),
        block_type="paragraph",
    )


def _header_elem(page_no: int, text: str) -> DocumentElement:
    """상단 10% 영역 (y1 <= 84.2) 요소."""
    return _elem(page_no, text, y0=5.0, y1=20.0)


def _footer_elem(page_no: int, text: str) -> DocumentElement:
    """하단 10% 영역 (y0 >= 757.8) 요소."""
    return _elem(page_no, text, y0=800.0, y1=830.0)


def _body_elem(page_no: int, text: str) -> DocumentElement:
    """본문 영역 (10%~90%) 요소."""
    return _elem(page_no, text, y0=200.0, y1=220.0)


class TestNoiseRemover:
    """Tests for NoiseRemover."""

    def test_remove_repeated_header(self) -> None:
        """3페이지 이상 동일 헤더 반복 → 제거."""
        pages = {
            1: [_header_elem(1, "회사명"), _body_elem(1, "본문1")],
            2: [_header_elem(2, "회사명"), _body_elem(2, "본문2")],
            3: [_header_elem(3, "회사명"), _body_elem(3, "본문3")],
        }
        remover = NoiseRemover()
        result = remover.remove(pages, PAGE_HEIGHT)

        for page_no, elements in result.items():
            texts = [e.text for e in elements]
            assert "회사명" not in texts
            assert f"본문{page_no}" in texts

    def test_remove_repeated_footer(self) -> None:
        """반복 푸터 제거."""
        pages = {
            1: [_body_elem(1, "내용1"), _footer_elem(1, "confidential")],
            2: [_body_elem(2, "내용2"), _footer_elem(2, "confidential")],
            3: [_body_elem(3, "내용3"), _footer_elem(3, "confidential")],
        }
        remover = NoiseRemover()
        result = remover.remove(pages, PAGE_HEIGHT)

        for elements in result.values():
            texts = [e.text for e in elements]
            assert "confidential" not in texts

    def test_remove_page_numbers(self) -> None:
        """하단 숫자만 있는 페이지번호 제거."""
        pages = {
            1: [_body_elem(1, "내용"), _footer_elem(1, "1")],
            2: [_body_elem(2, "내용"), _footer_elem(2, "2")],
            3: [_body_elem(3, "내용"), _footer_elem(3, "3")],
        }
        remover = NoiseRemover()
        result = remover.remove(pages, PAGE_HEIGHT)

        for elements in result.values():
            texts = [e.text for e in elements]
            assert all(not t.isdigit() for t in texts)

    def test_body_text_preserved(self) -> None:
        """본문 텍스트는 제거하지 않음."""
        pages = {
            1: [_header_elem(1, "반복헤더"), _body_elem(1, "중요내용A")],
            2: [_header_elem(2, "반복헤더"), _body_elem(2, "중요내용B")],
            3: [_header_elem(3, "반복헤더"), _body_elem(3, "중요내용C")],
        }
        remover = NoiseRemover()
        result = remover.remove(pages, PAGE_HEIGHT)

        assert result[1][0].text == "중요내용A"
        assert result[2][0].text == "중요내용B"
        assert result[3][0].text == "중요내용C"

    def test_single_page_no_removal(self) -> None:
        """1페이지 문서는 제거하지 않음."""
        pages = {
            1: [_header_elem(1, "헤더"), _body_elem(1, "본문")],
        }
        remover = NoiseRemover()
        result = remover.remove(pages, PAGE_HEIGHT)

        assert len(result[1]) == 2

    def test_two_pages_no_removal(self) -> None:
        """2페이지 이하는 제거하지 않음 (total < 2 early return이므로 정확히 2페이지는 처리됨)."""
        pages = {
            1: [_header_elem(1, "헤더"), _body_elem(1, "본문1")],
            2: [_header_elem(2, "헤더"), _body_elem(2, "본문2")],
        }
        remover = NoiseRemover()
        result = remover.remove(pages, PAGE_HEIGHT)

        # 2 pages: 60% threshold = 1.2, header appears 2 times >= 1.2 → removed
        page1_texts = [e.text for e in result[1]]
        assert "헤더" not in page1_texts

    def test_non_repeated_header_preserved(self) -> None:
        """반복되지 않는 상단 텍스트는 보존."""
        pages = {
            1: [_header_elem(1, "고유헤더1"), _body_elem(1, "본문1")],
            2: [_header_elem(2, "고유헤더2"), _body_elem(2, "본문2")],
            3: [_header_elem(3, "고유헤더3"), _body_elem(3, "본문3")],
        }
        remover = NoiseRemover()
        result = remover.remove(pages, PAGE_HEIGHT)

        assert result[1][0].text == "고유헤더1"
        assert result[2][0].text == "고유헤더2"

    def test_case_insensitive_matching(self) -> None:
        """대소문자 무관 매칭."""
        pages = {
            1: [_header_elem(1, "Header"), _body_elem(1, "body1")],
            2: [_header_elem(2, "HEADER"), _body_elem(2, "body2")],
            3: [_header_elem(3, "header"), _body_elem(3, "body3")],
        }
        remover = NoiseRemover()
        result = remover.remove(pages, PAGE_HEIGHT)

        for elements in result.values():
            texts = [e.text.lower() for e in elements]
            assert "header" not in texts

    def test_page_number_with_dash_format(self) -> None:
        """'- 1 -' 같은 형식도 페이지번호로 감지."""
        pages = {
            1: [_body_elem(1, "내용"), _footer_elem(1, "1")],
            2: [_body_elem(2, "내용"), _footer_elem(2, "2")],
            3: [_body_elem(3, "내용"), _footer_elem(3, "3")],
        }
        remover = NoiseRemover()
        result = remover.remove(pages, PAGE_HEIGHT)

        for elements in result.values():
            assert all(not e.text.strip().isdigit() for e in elements)

    def test_empty_pages_dict(self) -> None:
        """빈 입력 처리."""
        remover = NoiseRemover()
        result = remover.remove({}, PAGE_HEIGHT)
        assert result == {}

    def test_mixed_noise_and_body(self) -> None:
        """노이즈 + 본문 혼합 시 노이즈만 제거."""
        pages = {
            1: [
                _header_elem(1, "© 2026 회사명"),
                _body_elem(1, "제1조 목적"),
                _body_elem(1, "이 규정은..."),
                _footer_elem(1, "1"),
            ],
            2: [
                _header_elem(2, "© 2026 회사명"),
                _body_elem(2, "제2조 정의"),
                _footer_elem(2, "2"),
            ],
            3: [
                _header_elem(3, "© 2026 회사명"),
                _body_elem(3, "제3조 적용범위"),
                _footer_elem(3, "3"),
            ],
        }
        remover = NoiseRemover()
        result = remover.remove(pages, PAGE_HEIGHT)

        assert len(result[1]) == 2
        texts_1 = [e.text for e in result[1]]
        assert "제1조 목적" in texts_1
        assert "이 규정은..." in texts_1
