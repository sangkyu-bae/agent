"""PdfPyMuPdfExtractor — PDF 에서 이미지 후보를 추출한다.

Design Ref: multimodal-extractor §2.2 / §9.5 ImageExtractorPort 구현체.
- Plan FR-01: 페이지 내장 이미지 객체
  → ImageCandidate(page, bbox, bytes, 크기, 면적 비율, sha256)
- Plan FR-02: find_tables() 영역 → TABLE_IMAGE 렌더 후보.
  analysis 가 has_extractable_text=False 로 표시한 페이지는 전체 렌더 1장
  (PAGE_SCAN)으로 대표하고 그 페이지의 내장 이미지는 제외(중복 호출 방지).
- 필터·상한은 여기서 하지 않는다(도메인 Policy 책임). 순서는 페이지 → y → x.
"""

import hashlib
from collections.abc import Iterable
from typing import TYPE_CHECKING

import fitz  # PyMuPDF

from src.domain.multimodal.errors import ExtractionError, UnsupportedFormatError
from src.domain.multimodal.interfaces import ImageExtractorPort
from src.domain.multimodal.value_objects import BBox, ElementType, ImageCandidate

if TYPE_CHECKING:
    from src.domain.pdf_analyzer.schemas import AnalysisResult

_PNG = "image/png"
_JPEG = "image/jpeg"


class PdfPyMuPdfExtractor(ImageExtractorPort):
    supported_extensions: frozenset[str] = frozenset({"pdf"})

    def __init__(self, render_dpi: int = 144, table_dpi: int = 144) -> None:
        self._render_dpi = render_dpi
        self._table_dpi = table_dpi

    def extract(
        self,
        file_bytes: bytes,
        filename: str,
        analysis: "AnalysisResult | None",
    ) -> list[ImageCandidate]:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in self.supported_extensions:
            raise UnsupportedFormatError(ext, tuple(sorted(self.supported_extensions)))
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception as e:  # fitz 는 다양한 예외 타입을 던진다
            raise ExtractionError(f"cannot open pdf '{filename}': {e}") from e
        try:
            scanned = _scanned_pages(analysis)
            out: list[ImageCandidate] = []
            for page in doc:
                out.extend(self._extract_page(page, page.number + 1 in scanned))
            return out
        finally:
            doc.close()

    def _extract_page(self, page: fitz.Page, is_scanned: bool) -> list[ImageCandidate]:
        page_no = page.number + 1
        page_area = page.rect.width * page.rect.height
        if is_scanned:
            return [self._render_page(page, page_no)]
        cands = list(_embedded_images(page, page_no, page_area))
        cands.extend(self._table_regions(page, page_no, page_area))
        cands.sort(key=lambda c: (c.page, c.bbox.y0, c.bbox.x0))
        return cands

    def _render_page(self, page: fitz.Page, page_no: int) -> ImageCandidate:
        pix = page.get_pixmap(dpi=self._render_dpi, alpha=False)
        data = pix.tobytes("png")
        r = page.rect
        return _candidate(
            page_no, r, data, _PNG, pix.width, pix.height, 1.0, ElementType.PAGE_SCAN
        )

    def _table_regions(
        self, page: fitz.Page, page_no: int, page_area: float
    ) -> Iterable[ImageCandidate]:
        try:
            tables = page.find_tables()
        except (
            Exception
        ):  # 일부 페이지 구조에서 find_tables 가 실패할 수 있음 — 표 후보만 포기
            return []
        out: list[ImageCandidate] = []
        for t in tables.tables:
            rect = fitz.Rect(t.bbox)
            if rect.is_empty or rect.width < 1 or rect.height < 1:
                continue
            pix = page.get_pixmap(dpi=self._table_dpi, clip=rect, alpha=False)
            ratio = (
                min(1.0, (rect.width * rect.height) / page_area) if page_area else 0.0
            )
            out.append(
                _candidate(
                    page_no,
                    rect,
                    pix.tobytes("png"),
                    _PNG,
                    pix.width,
                    pix.height,
                    ratio,
                    ElementType.TABLE_IMAGE,
                )
            )
        return out


def _scanned_pages(analysis: "AnalysisResult | None") -> set[int]:
    if analysis is None:
        return set()
    return {
        pf.page_number for pf in analysis.page_features if not pf.has_extractable_text
    }


def _embedded_images(
    page: fitz.Page, page_no: int, page_area: float
) -> Iterable[ImageCandidate]:
    doc = page.parent
    # 같은 xref 가 여러 번 배치되면 get_images 가 xref 를 반복 나열한다
    # — 1회만 처리(rects 가 배치 전부를 준다)
    seen_xrefs: set[int] = set()
    for info in page.get_images(full=True):
        xref = info[0]
        if xref in seen_xrefs:
            continue
        seen_xrefs.add(xref)
        rects = page.get_image_rects(xref)
        if not rects:
            continue
        data, mime, w, h = _image_payload(doc, xref)
        for rect in rects:
            ratio = (
                min(1.0, (rect.width * rect.height) / page_area) if page_area else 0.0
            )
            yield _candidate(page_no, rect, data, mime, w, h, ratio, ElementType.FIGURE)


def _image_payload(doc: fitz.Document, xref: int) -> tuple[bytes, str, int, int]:
    """원본 인코딩이 jpeg/png 면 그대로, 그 외(CMYK·마스크 등)는 PNG 로 정규화."""
    raw = doc.extract_image(xref)
    ext = raw.get("ext", "")
    if ext in ("png", "jpeg", "jpg"):
        mime = _JPEG if ext in ("jpeg", "jpg") else _PNG
        return raw["image"], mime, raw["width"], raw["height"]
    pix = fitz.Pixmap(doc, xref)
    if pix.n - pix.alpha >= 4:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    return pix.tobytes("png"), _PNG, pix.width, pix.height


def _candidate(
    page_no: int,
    rect: fitz.Rect,
    data: bytes,
    mime: str,
    width: int,
    height: int,
    ratio: float,
    hint: ElementType,
) -> ImageCandidate:
    return ImageCandidate(
        page=page_no,
        bbox=BBox(float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)),
        image_bytes=data,
        mime=mime,
        width=width,
        height=height,
        area_ratio=ratio,
        sha256=hashlib.sha256(data).hexdigest(),
        hint_type=hint,
    )
