"""PptxStyleExtractor (Design §2.3 / FR-03 / D4) — 원본 PPTX 도형 통계."""

from __future__ import annotations

import pytest
from src.domain.blueprint.errors import SampleExtractionError
from src.domain.blueprint.policies import (
    PaletteClusterPolicy,
    RepeatAssetPolicy,
    SizeHierarchyPolicy,
)
from src.infrastructure.blueprint.extractors.pptx_style_extractor import (
    PptxStyleExtractor,
)

from tests.fixtures.blueprint_samples import sample_pptx


@pytest.fixture(scope="module")
def stats():
    return PptxStyleExtractor().extract(sample_pptx(), "sample.pptx", max_pages=60)


def test_basic_shape_no_render(stats):
    assert stats.source_kind == "pptx"
    assert len(stats.pages) == 5
    assert stats.page_size == pytest.approx((13.333, 7.5), abs=0.01)
    assert all(p.render_png is None for p in stats.pages)  # D4: 렌더 없음
    assert set(stats.theme_fonts) >= {"major", "minor"}


def test_spans_from_text_frames(stats):
    p2 = stats.pages[1]
    title = next(s for s in p2.spans if s.text == "Contents")
    assert title.size == 20.0 and title.bold and title.font == "HeadFont"
    assert title.color == "#1F3A5F"
    assert 0.05 < title.box.x < 0.1
    body = next(s for s in p2.spans if s.text.startswith("1. Overview"))
    assert body.font == "BodyFont" and body.size == 14.0 and body.color == "#222222"


def test_pictures_repeat_logo_and_cover(stats):
    logo_shas = {img.sha256 for p in stats.pages[1:] for img in p.images}
    assert len(logo_shas) == 1
    cover = stats.pages[0].images[0]
    assert cover.box.area > 0.95
    assert sorted(a.kind for a in RepeatAssetPolicy.apply(stats)) == ["cover", "logo"]


def test_tables_and_charts(stats):
    assert len(stats.pages[3].tables) == 1 and stats.pages[3].tables[0].w > 0.7
    assert len(stats.pages[2].charts) == 1
    assert stats.pages[1].charts == () and stats.pages[1].tables == ()


def test_policies_on_pptx_stats(stats):
    palette = PaletteClusterPolicy.apply(stats)
    assert palette["primary"] == "#1F3A5F" and palette["accent1"] == "#E07A1F"
    sizes = SizeHierarchyPolicy.apply(stats)
    assert sizes.sizes == {"h1": 28.0, "h2": 20.0, "body": 14.0, "caption": 10.0}
    assert sizes.fonts == {"heading": "HeadFont", "body": "BodyFont"}


def test_max_pages_and_corrupt():
    short = PptxStyleExtractor().extract(sample_pptx(), "s.pptx", max_pages=3)
    assert len(short.pages) == 3
    with pytest.raises(SampleExtractionError):
        PptxStyleExtractor().extract(b"PK\x03\x04garbage", "x.pptx", max_pages=10)


def test_supported_extensions():
    assert PptxStyleExtractor.supported_extensions == ("pptx",)
