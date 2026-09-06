"""HtmlFontEmbedder 생성 팩토리 (Design §11.1 — DI 배선 중복 제거).

main.py 의 두 배선 지점(요청 스코프 / 앱 스코프)이 같은 설정으로 임베더를
만들도록 한 곳에 모은다.
"""
from __future__ import annotations

from pathlib import Path

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.document_font.font_subsetter import FontSubsetter
from src.infrastructure.document_font.html_font_embedder import HtmlFontEmbedder

# src/infrastructure/document_font/factory.py → 프로젝트 루트(idt/)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def resolve_font_dir(configured: str) -> Path:
    """설정의 상대경로를 프로젝트 루트 기준으로 해석한다."""
    path = Path(configured or "resources/fonts")
    return path if path.is_absolute() else _PROJECT_ROOT / path


def create_html_font_embedder(settings, logger: LoggerInterface) -> HtmlFontEmbedder:
    font_dir = resolve_font_dir(settings.document_font_dir)
    family = settings.document_font_family
    return HtmlFontEmbedder(
        subsetter=FontSubsetter(font_dir=font_dir, family=family),
        logger=logger,
        family=family,
        enabled=settings.document_font_embed_enabled,
        max_embed_kb=settings.document_font_max_embed_kb,
    )
