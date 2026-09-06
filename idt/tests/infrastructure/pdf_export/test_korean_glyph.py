"""pdf_export 한글 렌더링 통합 테스트 (Design §8.3 I-01·I-02, FR-07).

MCP 없이 실경로로 PDF 를 만들어 볼 수 있는 유일한 지점이라, "한글이 실제로
글리프를 갖는다"는 증거를 여기서 확보한다.
"""
from pathlib import Path

import pytest

from src.infrastructure.pdf_export.weasyprint_converter import WeasyprintConverter
from tests.support.pdf_glyph_check import check_glyphs

_FONT_DIR = Path(__file__).resolve().parents[3] / "resources" / "fonts"
_HAS_FONTS = (_FONT_DIR / "Pretendard-Regular.ttf").exists()

pytestmark = pytest.mark.skipif(not _HAS_FONTS, reason="폰트 자산 미반입")

# Design §8.6 — 제목·본문·표·굵은글씨를 포함한 한글 픽스처
_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "korean_document.html"
_KOREAN_HTML = _FIXTURE.read_text(encoding="utf-8")


def test_korean_pdf_has_no_notdef_glyphs():
    """I-01: 생성 PDF 의 한글 .notdef 비율 0% (Plan SC)."""
    pdf = WeasyprintConverter().convert(_KOREAN_HTML)

    result = check_glyphs(pdf)

    # verifiable=False 는 '폰트가 아예 안 심겼다'는 뜻 — 통과시키면 안 된다.
    assert result.verifiable, f"임베드 폰트 없음: {result.base_fonts}"
    assert result.is_broken is False, (
        f"글리프 누락 {result.notdef_codes}/{result.total_codes} "
        f"({result.strategy}) missing={result.missing_chars[:20]}"
    )


def test_korean_pdf_embeds_korean_font():
    """I-02: BaseFont 에 한글 폰트가 실제로 임베드된다."""
    pdf = WeasyprintConverter().convert(_KOREAN_HTML)

    result = check_glyphs(pdf)

    assert any("Pretendard" in name for name in result.base_fonts), (
        f"임베드된 폰트: {result.base_fonts}"
    )


def test_ascii_only_document_still_converts():
    """한글이 없어도 회귀 없이 변환된다."""
    pdf = WeasyprintConverter().convert("<h1>Report</h1><p>ok</p>")

    assert pdf.startswith(b"%PDF")


def test_caller_css_is_still_applied():
    """기존 계약: 호출자가 넘긴 css_content 가 유실되지 않는다."""
    pdf = WeasyprintConverter().convert(
        _KOREAN_HTML, css_content="h1{color:#333}"
    )

    assert pdf.startswith(b"%PDF")
