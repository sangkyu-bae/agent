"""pdf_glyph_check 검증기 자체를 검증한다 (Design §11.2 구현순서 2).

깨진 PDF(samples/test.pdf, 2026-09-04 진단 대상)를 골든 픽스처로 삼아
검사기가 실제 .notdef 매핑을 재현하는지 확인한다. 검사기를 먼저 신뢰할 수
있어야 이후 모든 시나리오(U/I/E)의 판정이 의미를 갖는다.
"""
from pathlib import Path

import pytest

from tests.support.pdf_glyph_check import check_glyphs

_SAMPLES = Path(__file__).resolve().parents[2] / "samples"
_BROKEN_PDF = _SAMPLES / "test.pdf"


@pytest.mark.skipif(not _BROKEN_PDF.exists(), reason="골든 깨짐 샘플 없음")
def test_detects_notdef_in_known_broken_pdf():
    """2026-09-04 실측: 세 폰트 합계 549 코드 중 472개가 CID 0."""
    result = check_glyphs(_BROKEN_PDF.read_bytes())

    assert result.strategy == "cmap-cid"
    assert result.verifiable is True
    assert result.total_codes == 549
    assert result.notdef_codes == 472
    assert result.ratio == pytest.approx(472 / 549, abs=1e-6)
    assert result.is_broken is True


@pytest.mark.skipif(not _BROKEN_PDF.exists(), reason="골든 깨짐 샘플 없음")
def test_reports_base_fonts_of_broken_pdf():
    """원인 규명에 필요한 폰트명이 결과에 포함된다."""
    result = check_glyphs(_BROKEN_PDF.read_bytes())

    assert any("DejaVu" in name for name in result.base_fonts)
    assert not any("Pretendard" in name for name in result.base_fonts)


def test_returns_no_fonts_for_non_pdf_bytes():
    """폰트를 못 찾으면 예외 대신 '검증 불가' 판정을 돌려준다.

    is_broken=False 지만 verifiable=False — 기본 14폰트로 한글을 그린 PDF 가
    조용히 통과하던 사각지대를 막는 신호다.
    """
    result = check_glyphs(b"not a pdf at all")

    assert result.strategy == "no-fonts"
    assert result.total_codes == 0
    assert result.ratio == 0.0
    assert result.is_broken is False
    assert result.verifiable is False


def test_empty_bytes_are_safe():
    result = check_glyphs(b"")

    assert result.strategy == "no-fonts"
    assert result.is_broken is False
