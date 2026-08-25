"""PdfStyleExtractor — PyMuPDF 로 Golden Sample PDF 의 스타일 통계를 뽑는다.

Design Ref: golden-sample-blueprint §2.3 / Plan FR-02
- span(폰트·크기·굵기·색·bbox) / 표 영역(find_tables) / 내장 이미지(xref 중복 제거) /
  페이지 렌더 PNG(비전 분류 입력). 좌표는 RelBox(0..1) 로 정규화 (D1).
- 손상 파일·페이지 0 → SampleExtractionError (§6.1 415).
"""

from __future__ import annotations

import hashlib

import fitz

from src.domain.blueprint.errors import SampleExtractionError
from src.domain.blueprint.value_objects import (
    FillRect,
    ImageRef,
    PageStats,
    RelBox,
    SampleStats,
    TextSpan,
)

_BOLD_FLAG = 16
_PT_PER_INCH = 72.0
_MIN_FILL_AREA = 0.0005  # 선·점 수준 잡음 제외
_RASTER_EXT = {"png": "image/png", "jpeg": "image/jpeg", "jpg": "image/jpeg"}


def _rel(rect: fitz.Rect, w: float, h: float) -> RelBox | None:
    x0, y0 = max(0.0, rect.x0 / w), max(0.0, rect.y0 / h)
    x1, y1 = min(1.0, rect.x1 / w), min(1.0, rect.y1 / h)
    if x1 - x0 <= 0 or y1 - y0 <= 0:
        return None
    return RelBox(x=x0, y=y0, w=x1 - x0, h=y1 - y0)


def _hex(color: int) -> str:
    return f"#{color & 0xFFFFFF:06X}"


class PdfStyleExtractor:
    supported_extensions: tuple[str, ...] = ("pdf",)

    def __init__(self, render_dpi: int = 72) -> None:
        self._render_dpi = render_dpi

    def extract(self, data: bytes, filename: str, max_pages: int) -> SampleStats:
        try:
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:  # noqa: BLE001 — 손상 파일은 415 로 매핑
            raise SampleExtractionError(f"cannot open pdf: {exc}") from exc
        try:
            if doc.page_count == 0:
                raise SampleExtractionError("pdf has no pages")
            first = doc[0].rect
            pages = tuple(
                self._page(doc, i) for i in range(min(doc.page_count, max_pages))
            )
            return SampleStats(
                source_kind="pdf",
                page_size=(first.width / _PT_PER_INCH, first.height / _PT_PER_INCH),
                pages=pages,
                theme_fonts={},
            )
        except SampleExtractionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise SampleExtractionError(f"pdf parse failed: {exc}") from exc
        finally:
            doc.close()

    # ── internal ──────────────────────────────────────────────────────────────

    def _page(self, doc: fitz.Document, index: int) -> PageStats:
        page = doc[index]
        w, h = page.rect.width, page.rect.height
        spans = tuple(self._spans(page, w, h))
        rects = tuple(self._rects(page, w, h))
        return PageStats(
            number=index + 1,
            width=w,
            height=h,
            spans=spans,
            images=tuple(self._images(doc, page, w, h)),
            tables=tuple(self._tables(page, w, h)),
            has_text=any(s.text.strip() for s in spans),
            render_png=page.get_pixmap(dpi=self._render_dpi).tobytes("png"),
            fills=tuple((r.color, r.box.area) for r in rects),
            rects=rects,
        )

    @staticmethod
    def _spans(page: fitz.Page, w: float, h: float):
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    box = _rel(fitz.Rect(span["bbox"]), w, h)
                    if not text.strip() or box is None:
                        continue
                    font = span.get("font", "")
                    bold = (
                        bool(span.get("flags", 0) & _BOLD_FLAG)
                        or "bold" in font.lower()
                    )
                    yield TextSpan(
                        text=text,
                        font=font,
                        size=round(float(span.get("size", 0.0)), 1),
                        bold=bold,
                        color=_hex(int(span.get("color", 0))),
                        box=box,
                    )

    @staticmethod
    def _images(doc: fitz.Document, page: fitz.Page, w: float, h: float):
        seen: set[int] = set()
        for info in page.get_image_info(xrefs=True):
            xref = info.get("xref", 0)
            if not xref or xref in seen:
                continue
            seen.add(xref)
            box = _rel(fitz.Rect(info["bbox"]), w, h)
            if box is None:
                continue
            data, mime = _image_bytes(doc, xref)
            yield ImageRef(
                sha256=hashlib.sha256(data).hexdigest(),
                mime=mime,
                width=int(info.get("width", 0)),
                height=int(info.get("height", 0)),
                box=box,
                data=data,
            )

    @staticmethod
    def _rects(page: fitz.Page, w: float, h: float):
        """벡터 채움 사각형 (색, RelBox) — 팔레트·장식(FR-06) 입력. 잡음 면적 제외."""
        for d in page.get_drawings():
            fill = d.get("fill")
            rect = d.get("rect")
            if not fill or rect is None or rect.is_empty:
                continue
            box = _rel(rect, w, h)
            if box is None or box.area < _MIN_FILL_AREA:
                continue
            r, g, b = (int(round(c * 255)) for c in fill[:3])
            yield FillRect(color=f"#{r:02X}{g:02X}{b:02X}", box=box)

    @staticmethod
    def _tables(page: fitz.Page, w: float, h: float):
        for table in page.find_tables().tables:
            box = _rel(fitz.Rect(table.bbox), w, h)
            if box is not None:
                yield box


def _image_bytes(doc: fitz.Document, xref: int) -> tuple[bytes, str]:
    raw = doc.extract_image(xref)
    ext = (raw or {}).get("ext", "")
    if ext in _RASTER_EXT:
        return raw["image"], _RASTER_EXT[ext]
    pix = fitz.Pixmap(doc, xref)
    if pix.n - pix.alpha >= 4:  # CMYK 등 → RGB
        pix = fitz.Pixmap(fitz.csRGB, pix)
    return pix.tobytes("png"), "image/png"
