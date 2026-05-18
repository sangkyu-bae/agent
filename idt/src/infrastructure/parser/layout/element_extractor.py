"""PyMuPDF get_text("dict")를 DocumentElement 리스트로 변환."""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.parser.document_element import BoundingBox, DocumentElement
from src.infrastructure.logging import get_logger

if TYPE_CHECKING:
    import fitz

logger = get_logger(__name__)


class ElementExtractor:
    """PyMuPDF 페이지에서 좌표 기반 원자 요소를 추출."""

    def extract(
        self, page: fitz.Page, page_no: int
    ) -> list[DocumentElement]:
        """한 페이지에서 텍스트 블록을 DocumentElement로 변환."""
        try:
            data = page.get_text("dict")
        except Exception as e:
            logger.error("Failed to extract text from page", exception=e, page_no=page_no)
            return []

        elements: list[DocumentElement] = []
        for block in data.get("blocks", []):
            if block.get("type") == 0:
                elements.extend(self._extract_text_block(block, page_no))
        return elements

    def extract_tables(
        self, page: fitz.Page, page_no: int
    ) -> list[DocumentElement]:
        """PyMuPDF find_tables()로 표 영역을 별도 추출."""
        try:
            tables = page.find_tables()
        except Exception as e:
            logger.error("Failed to find tables", exception=e, page_no=page_no)
            return []

        elements: list[DocumentElement] = []
        for table in tables:
            element = self._table_to_element(table, page_no)
            if element:
                elements.append(element)
        return elements

    def _extract_text_block(
        self, block: dict, page_no: int
    ) -> list[DocumentElement]:
        results: list[DocumentElement] = []
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(span.get("text", "") for span in spans)
            if not text.strip():
                continue

            font_size = spans[0].get("size", 0.0) if spans else 0.0
            is_bold = any(
                "Bold" in (s.get("font", "") or "") for s in spans
            )

            line_bbox = line.get("bbox", (0, 0, 0, 0))
            bbox = BoundingBox(
                x0=line_bbox[0], y0=line_bbox[1],
                x1=line_bbox[2], y1=line_bbox[3],
            )

            results.append(DocumentElement(
                page_no=page_no,
                text=text.strip(),
                bbox=bbox,
                block_type="paragraph",
                font_size=font_size,
                is_bold=is_bold,
            ))
        return results

    def _table_to_element(
        self, table: object, page_no: int
    ) -> DocumentElement | None:
        try:
            bbox_tuple = table.bbox  # type: ignore[attr-defined]
            rows = table.extract()  # type: ignore[attr-defined]
        except Exception:
            return None

        if not rows:
            return None

        table_bbox = BoundingBox(
            x0=bbox_tuple[0], y0=bbox_tuple[1],
            x1=bbox_tuple[2], y1=bbox_tuple[3],
        )

        md_lines: list[str] = []
        header = getattr(table, "header", None)
        if header and getattr(header, "names", None):
            md_lines.append("| " + " | ".join(str(h) for h in header.names) + " |")
            md_lines.append("| " + " | ".join("---" for _ in header.names) + " |")

        for row in rows:
            md_lines.append(
                "| " + " | ".join(str(c) if c else "" for c in row) + " |"
            )

        return DocumentElement(
            page_no=page_no,
            text="\n".join(md_lines),
            bbox=table_bbox,
            block_type="table",
            font_size=0.0,
        )
