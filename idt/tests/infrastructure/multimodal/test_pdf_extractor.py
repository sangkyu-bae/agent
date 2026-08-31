"""PdfPyMuPdfExtractor 단위 테스트 — Design §8.5 합성 PDF fixture, FR-01/FR-02.

fixture 구성(코드로 합성, 바이너리 커밋 없음):
  p1: 큰 그림 1(400x300) + 48px 아이콘 2개(동일 바이트 → 동일 sha256) + 본문 텍스트
  p2: 텍스트 + 표(find_tables 가 잡는 격자)  → TABLE_IMAGE 후보
  p3: 텍스트 없는 페이지(스캔형)             → PAGE_SCAN 후보
"""

from __future__ import annotations

import hashlib

import fitz
import pytest
from src.domain.multimodal.errors import ExtractionError, UnsupportedFormatError
from src.domain.multimodal.value_objects import ElementType
from src.domain.pdf_analyzer.schemas import (
    AnalysisResult,
    PageFeatures,
    PDFDocumentType,
    SummaryMetrics,
)
from src.infrastructure.multimodal.extractors.pdf_pymupdf_extractor import (
    PdfPyMuPdfExtractor,
)


def _png(w: int, h: int, color: tuple[int, int, int]) -> bytes:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, w, h), False)
    pix.clear_with(0)
    for x in range(w):
        for y in range(h):
            pix.set_pixel(x, y, color)
    return pix.tobytes("png")


def _draw_table(page: fitz.Page, rect: fitz.Rect, rows: int = 4, cols: int = 3) -> None:
    shape = page.new_shape()
    rw, ch = rect.width / cols, rect.height / rows
    for r in range(rows + 1):
        y = rect.y0 + r * ch
        shape.draw_line((rect.x0, y), (rect.x1, y))
    for c in range(cols + 1):
        x = rect.x0 + c * rw
        shape.draw_line((x, rect.y0), (x, rect.y1))
    shape.finish(width=1)
    shape.commit()
    for r in range(rows):
        for c in range(cols):
            page.insert_text(
                (rect.x0 + c * rw + 4, rect.y0 + r * ch + 14), f"r{r}c{c}", fontsize=9
            )


@pytest.fixture(scope="module")
def sample_pdf() -> bytes:
    doc = fitz.open()
    big = _png(400, 300, (200, 30, 30))
    icon = _png(48, 48, (30, 30, 200))

    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((72, 60), "Page one with a figure and two icons", fontsize=12)
    p1.insert_image(fitz.Rect(72, 100, 472, 400), stream=big)
    p1.insert_image(fitz.Rect(500, 20, 548, 68), stream=icon)
    p1.insert_image(fitz.Rect(500, 780, 548, 828), stream=icon)

    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((72, 60), "Page two has a table", fontsize=12)
    _draw_table(p2, fitz.Rect(72, 100, 500, 300))

    p3 = doc.new_page(width=595, height=842)
    p3.insert_image(fitz.Rect(0, 0, 595, 842), stream=_png(300, 420, (120, 120, 120)))

    data = doc.tobytes()
    doc.close()
    return data


def _analysis_with_page3_scanned() -> AnalysisResult:
    pf = [
        PageFeatures(
            page_number=1,
            text_char_count=40,
            image_count=3,
            image_area_ratio=0.25,
            table_count=0,
            has_extractable_text=True,
        ),
        PageFeatures(
            page_number=2,
            text_char_count=30,
            image_count=0,
            image_area_ratio=0.0,
            table_count=1,
            has_extractable_text=True,
        ),
        PageFeatures(
            page_number=3,
            text_char_count=0,
            image_count=1,
            image_area_ratio=1.0,
            table_count=0,
            has_extractable_text=False,
        ),
    ]
    return AnalysisResult(
        document_type=PDFDocumentType.MULTIMODAL,
        confidence=0.9,
        total_pages=3,
        sampled_pages=3,
        page_features=pf,
        summary_metrics=SummaryMetrics(
            avg_text_chars=23,
            avg_image_count=1.3,
            avg_image_area_ratio=0.4,
            avg_table_count=0.3,
            extractable_text_ratio=0.66,
        ),
    )


def test_supported_extensions_is_pdf_only():
    assert PdfPyMuPdfExtractor().supported_extensions == frozenset({"pdf"})


def test_extracts_embedded_images_with_geometry_and_hash(sample_pdf: bytes):
    cands = PdfPyMuPdfExtractor().extract(sample_pdf, "sample.pdf", analysis=None)
    figures = [c for c in cands if c.hint_type is ElementType.FIGURE and c.page == 1]
    assert len(figures) == 3
    big = max(figures, key=lambda c: c.width)
    assert (big.width, big.height) == (400, 300)
    assert big.mime == "image/png"
    assert 0.2 < big.area_ratio < 0.3
    assert big.bbox.x0 == pytest.approx(72, abs=1) and big.bbox.y0 == pytest.approx(
        100, abs=1
    )
    assert big.sha256 == hashlib.sha256(big.image_bytes).hexdigest()
    icons = [c for c in figures if c.width == 48]
    assert len(icons) == 2 and icons[0].sha256 == icons[1].sha256


def test_table_region_becomes_table_image_candidate(sample_pdf: bytes):
    cands = PdfPyMuPdfExtractor().extract(sample_pdf, "sample.pdf", analysis=None)
    tables = [c for c in cands if c.hint_type is ElementType.TABLE_IMAGE]
    assert len(tables) >= 1
    t = tables[0]
    assert t.page == 2 and t.mime == "image/png" and t.width > 100
    assert 0.05 < t.area_ratio < 0.5


def test_page_scan_only_for_pages_without_extractable_text(sample_pdf: bytes):
    ex = PdfPyMuPdfExtractor()
    without = ex.extract(sample_pdf, "sample.pdf", analysis=None)
    assert not [c for c in without if c.hint_type is ElementType.PAGE_SCAN]

    with_analysis = ex.extract(
        sample_pdf, "sample.pdf", analysis=_analysis_with_page3_scanned()
    )
    scans = [c for c in with_analysis if c.hint_type is ElementType.PAGE_SCAN]
    assert [s.page for s in scans] == [3]
    assert scans[0].area_ratio == 1.0 and scans[0].width > 595  # render_dpi=144 → 2x


def test_page_scan_replaces_embedded_images_of_that_page(sample_pdf: bytes):
    """스캔 페이지는 전체 렌더 1장으로 대표.

    같은 페이지의 내장 이미지는 중복 호출 방지로 제외.
    """
    cands = PdfPyMuPdfExtractor().extract(
        sample_pdf, "sample.pdf", analysis=_analysis_with_page3_scanned()
    )
    page3 = [c for c in cands if c.page == 3]
    assert len(page3) == 1 and page3[0].hint_type is ElementType.PAGE_SCAN


def test_candidates_are_ordered_by_page_then_position(sample_pdf: bytes):
    cands = PdfPyMuPdfExtractor().extract(sample_pdf, "sample.pdf", analysis=None)
    pages = [c.page for c in cands]
    assert pages == sorted(pages)


def test_rejects_non_pdf_extension():
    with pytest.raises(UnsupportedFormatError):
        PdfPyMuPdfExtractor().extract(b"%PDF", "a.docx", analysis=None)


def test_corrupt_bytes_raise_extraction_error():
    with pytest.raises(ExtractionError):
        PdfPyMuPdfExtractor().extract(b"not a pdf at all", "x.pdf", analysis=None)
