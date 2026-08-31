"""PdfStyleExtractor (Design §2.3 / FR-02) — 합성 PDF 통계·좌표·반복 이미지 검증."""

from __future__ import annotations

import fitz
import pytest
from src.domain.blueprint.errors import SampleExtractionError
from src.domain.blueprint.policies import (
    PaletteClusterPolicy,
    RepeatAssetPolicy,
    SizeHierarchyPolicy,
)
from src.infrastructure.blueprint.extractors.pdf_style_extractor import (
    PdfStyleExtractor,
)

from tests.fixtures.blueprint_samples import sample_pdf


@pytest.fixture(scope="module")
def stats():
    return PdfStyleExtractor(render_dpi=36).extract(
        sample_pdf(), "sample.pdf", max_pages=60
    )


def test_basic_shape(stats):
    assert stats.source_kind == "pdf"
    assert len(stats.pages) == 5
    assert stats.page_size == pytest.approx((13.333, 7.5), abs=0.01)
    assert [p.number for p in stats.pages] == [1, 2, 3, 4, 5]
    assert all(p.render_png and p.render_png[:4] == b"\x89PNG" for p in stats.pages)


def test_spans_carry_font_size_bold_color_and_rel_box(stats):
    p2 = stats.pages[1]
    title = next(s for s in p2.spans if s.text.startswith("Contents"))
    assert title.size == pytest.approx(20.0, abs=0.5)
    assert title.bold is True
    assert "Bold" in title.font
    assert title.color == "#1F3A5F"
    assert 0.05 < title.box.x < 0.12 and 0.08 < title.box.y < 0.16
    body = next(s for s in p2.spans if s.text.startswith("1. Overview"))
    assert body.bold is False and body.color == "#222222"
    assert body.size == pytest.approx(14.0, abs=0.5)


def test_images_repeat_logo_and_cover_with_same_sha(stats):
    logo_shas = [
        img.sha256 for p in stats.pages[1:] for img in p.images if img.box.y < 0.2
    ]
    assert len(logo_shas) == 4 and len(set(logo_shas)) == 1
    cover = max(stats.pages[0].images, key=lambda i: i.box.area)
    assert cover.box.area > 0.95
    assert cover.data[:4] == b"\x89PNG" and cover.mime == "image/png"


def test_tables_detected_on_table_page_only(stats):
    assert len(stats.pages[3].tables) >= 1
    assert stats.pages[3].tables[0].w > 0.5
    assert stats.pages[1].tables == ()


def test_chart_page_has_one_off_content_image(stats):
    p3 = stats.pages[2]
    content = [i for i in p3.images if i.box.y > 0.2]
    assert len(content) == 1 and 0.3 < content[0].box.w < 0.6


def test_max_pages_limits_and_has_text(stats):
    short = PdfStyleExtractor(render_dpi=36).extract(sample_pdf(), "s.pdf", max_pages=2)
    assert len(short.pages) == 2
    assert all(p.has_text for p in stats.pages)


def test_policies_on_real_stats(stats):
    palette = PaletteClusterPolicy.apply(stats)
    assert palette["text"] == "#222222"
    assert palette["primary"] == "#1F3A5F"
    assert palette["accent1"] == "#E07A1F"
    sizes = SizeHierarchyPolicy.apply(stats)
    assert sizes.sizes["h1"] == 28.0 and sizes.sizes["body"] == 14.0
    assert sizes.sizes["h2"] == 20.0 and sizes.sizes["caption"] == 10.0
    assert "Bold" in sizes.fonts["heading"] and "Bold" not in sizes.fonts["body"]
    assets = RepeatAssetPolicy.apply(stats)
    assert sorted(a.kind for a in assets) == ["cover", "logo"]


def test_corrupt_pdf_raises_extraction_error():
    with pytest.raises(SampleExtractionError):
        PdfStyleExtractor().extract(b"%PDF-not-really", "x.pdf", max_pages=10)


def test_supported_extensions():
    assert PdfStyleExtractor.supported_extensions == ("pdf",)


def test_fills_collected_from_vector_shapes():
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(100, 100, 580, 400))  # 약 0.29 면적
    shape.finish(fill=(0xE0 / 255, 0x7A / 255, 0x1F / 255), color=None)
    shape.draw_rect(fitz.Rect(0, 0, 960, 540))  # 전면 배경
    shape.finish(fill=(0.12, 0.23, 0.37), color=None)
    shape.commit()
    data = doc.tobytes()
    doc.close()
    st = PdfStyleExtractor(render_dpi=20).extract(data, "f.pdf", 5)
    fills = dict(st.pages[0].fills)
    assert fills["#E07A1F"] == pytest.approx(0.2778, abs=0.01)
    assert "#1F3B5E" in fills and fills["#1F3B5E"] > 0.9


def test_rects_carry_color_and_rel_box_excluding_tiny_shapes():
    """style-fidelity FR-06: 채움 사각형은 좌표와 함께 rects 로도 수집된다."""
    doc = fitz.open()
    page = doc.new_page(width=960, height=540)
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(0, 502, 960, 540))  # 푸터 띠 (0,0.93,1,0.07)
    shape.finish(fill=(0xF2 / 255, 0xF4 / 255, 0xF5 / 255), color=None)
    shape.draw_rect(fitz.Rect(10, 10, 12, 12))  # 잡음
    shape.finish(fill=(0, 0, 0), color=None)
    shape.commit()
    data = doc.tobytes()
    doc.close()
    st = PdfStyleExtractor(render_dpi=20).extract(data, "r.pdf", 5)
    (rect,) = st.pages[0].rects
    assert rect.color == "#F2F4F5"
    assert rect.box.x == pytest.approx(0.0, abs=0.01)
    assert rect.box.y == pytest.approx(0.93, abs=0.01)
    assert rect.box.w == pytest.approx(1.0, abs=0.01)
    assert rect.box.h == pytest.approx(0.07, abs=0.01)
