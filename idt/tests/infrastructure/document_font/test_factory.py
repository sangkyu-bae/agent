"""create_html_font_embedder DI 팩토리 테스트 (Design §11.1).

main.py 의 두 배선 지점이 같은 설정을 쓰도록 팩토리에 모았으므로,
설정 → 임베더 매핑이 어긋나면 여기서 잡힌다.
"""
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.infrastructure.document_font.factory import (
    create_html_font_embedder,
    resolve_font_dir,
)

_FONT_DIR = Path(__file__).resolve().parents[3] / "resources" / "fonts"
_HAS_FONTS = (_FONT_DIR / "Pretendard-Regular.ttf").exists()


class _NullLogger:
    def __getattr__(self, name):
        return lambda *a, **k: None


@dataclass
class _Settings:
    document_font_dir: str = "resources/fonts"
    document_font_family: str = "Pretendard"
    document_font_embed_enabled: bool = True
    document_font_max_embed_kb: int = 200


def test_relative_font_dir_resolves_under_project_root():
    resolved = resolve_font_dir("resources/fonts")

    assert resolved.is_absolute()
    assert resolved.name == "fonts"
    assert (resolved.parent / "fonts").exists()


def test_absolute_font_dir_is_kept(tmp_path: Path):
    assert resolve_font_dir(str(tmp_path)) == tmp_path


def test_blank_font_dir_falls_back_to_default():
    assert resolve_font_dir("").name == "fonts"


@pytest.mark.skipif(not _HAS_FONTS, reason="폰트 자산 미반입")
def test_created_embedder_embeds_fonts():
    embedder = create_html_font_embedder(_Settings(), _NullLogger())

    result = embedder.wrap("<h1>위기</h1>", request_id="r-1")

    assert result.applied is True
    assert "@font-face" in result.html


def test_disabled_setting_is_honoured():
    embedder = create_html_font_embedder(
        _Settings(document_font_embed_enabled=False), _NullLogger()
    )

    result = embedder.wrap("<h1>위기</h1>", request_id="r-1")

    assert result.applied is False
    assert result.reason == "font embed disabled"


@pytest.mark.skipif(not _HAS_FONTS, reason="폰트 자산 미반입")
def test_max_embed_kb_setting_drives_adaptive_fallback():
    embedder = create_html_font_embedder(
        _Settings(document_font_max_embed_kb=1), _NullLogger()
    )

    result = embedder.wrap("<p>본문 보고서</p>", request_id="r-1")

    assert {font.weight for font in result.fonts} == {400}
