"""FontSubsetter 단위 테스트 (Design §8.2 U-03·U-04)."""
from pathlib import Path

import pytest

from src.infrastructure.document_font.font_subsetter import FontSubsetter

_FONT_DIR = Path(__file__).resolve().parents[3] / "resources" / "fonts"
_HAS_FONTS = (_FONT_DIR / "Pretendard-Regular.ttf").exists()

pytestmark = pytest.mark.skipif(not _HAS_FONTS, reason="폰트 자산 미반입")


@pytest.fixture
def subsetter() -> FontSubsetter:
    return FontSubsetter(font_dir=_FONT_DIR, family="Pretendard")


def test_subsets_korean_characters(subsetter: FontSubsetter):
    """U-03: 한글 서브셋이 만들어지고 누락 문자가 없다."""
    font = subsetter.subset(400, frozenset("위기보고서분석개요"))

    assert font.family == "Pretendard"
    assert font.weight == 400
    assert font.byte_size > 0
    assert font.missing_chars == ()
    assert font.data_uri.startswith("data:font/ttf;base64,")


def test_subset_is_far_smaller_than_original(subsetter: FontSubsetter):
    """Plan NFR: 페이로드 증가분 통제의 근거."""
    original = (_FONT_DIR / "Pretendard-Regular.ttf").stat().st_size
    font = subsetter.subset(400, frozenset("위기보고서"))

    assert font.byte_size < original / 10


def test_reports_missing_glyphs_without_raising(subsetter: FontSubsetter):
    """U-04: 폰트에 없는 글자는 예외가 아니라 missing_chars 로 보고된다."""
    rare = "\U0002000b"  # CJK 확장 B — Pretendard 미수록
    font = subsetter.subset(400, frozenset("본문" + rare))

    assert rare in font.missing_chars
    assert "본" not in font.missing_chars
    assert font.byte_size > 0


def test_bold_weight_uses_bold_asset(subsetter: FontSubsetter):
    font = subsetter.subset(700, frozenset("굵게"))

    assert font.weight == 700
    assert font.byte_size > 0


def test_missing_font_file_raises(tmp_path: Path):
    """자산이 없으면 서브세터는 실패를 알린다 (폴백 판단은 임베더 책임)."""
    subsetter = FontSubsetter(font_dir=tmp_path, family="Pretendard")

    with pytest.raises(FileNotFoundError):
        subsetter.subset(400, frozenset("가"))


def test_empty_charset_still_produces_valid_font(subsetter: FontSubsetter):
    font = subsetter.subset(400, frozenset())

    assert font.byte_size > 0
    assert font.missing_chars == ()
