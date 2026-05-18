"""7단계 레이아웃 분석 파이프라인 오케스트레이터."""
from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.documents import Document

from src.domain.parser.document_element import DocumentElement
from src.domain.parser.parse_quality import ParseQualityScore
from src.domain.parser.value_objects import DocumentMetadata, generate_document_id
from src.infrastructure.parser.layout.column_detector import (
    ColumnDetector,
    LayoutType,
)
from src.infrastructure.parser.layout.element_extractor import ElementExtractor
from src.infrastructure.parser.layout.noise_remover import NoiseRemover
from src.infrastructure.parser.layout.quality_scorer import QualityScorer
from src.infrastructure.parser.layout.reading_order import (
    ReadingOrderReconstructor,
)
from src.infrastructure.parser.layout.section_builder import SectionBuilder
from src.infrastructure.parser.layout.table_handler import TableHandler

if TYPE_CHECKING:
    import fitz


class LayoutAnalyzer:
    """7단계 레이아웃 분석 파이프라인 오케스트레이터."""

    def __init__(
        self,
        element_extractor: ElementExtractor | None = None,
        noise_remover: NoiseRemover | None = None,
        column_detector: ColumnDetector | None = None,
        reading_order: ReadingOrderReconstructor | None = None,
        table_handler: TableHandler | None = None,
        section_builder: SectionBuilder | None = None,
        quality_scorer: QualityScorer | None = None,
    ) -> None:
        self._extractor = element_extractor or ElementExtractor()
        self._noise_remover = noise_remover or NoiseRemover()
        self._column_detector = column_detector or ColumnDetector()
        self._reading_order = reading_order or ReadingOrderReconstructor()
        self._table_handler = table_handler or TableHandler()
        self._section_builder = section_builder or SectionBuilder()
        self._quality_scorer = quality_scorer or QualityScorer()

    def analyze(
        self,
        pdf_doc: fitz.Document,
        filename: str,
        user_id: str,
    ) -> tuple[list[Document], ParseQualityScore]:
        """PDF 전체를 분석하여 Document 리스트 + 품질 점수 반환."""
        document_id = generate_document_id(filename)
        total_pages = pdf_doc.page_count

        all_documents: list[Document] = []
        page_scores: list[ParseQualityScore] = []

        pages_elements: dict[int, list[DocumentElement]] = {}
        for page_num in range(total_pages):
            page = pdf_doc[page_num]
            text_elements = self._extractor.extract(page, page_num + 1)
            table_elements = self._extractor.extract_tables(page, page_num + 1)
            pages_elements[page_num + 1] = text_elements + table_elements

        page_height = (
            pdf_doc[0].rect.height if total_pages > 0 else 842.0
        )
        page_width = pdf_doc[0].rect.width if total_pages > 0 else 595.0
        pages_elements = self._noise_remover.remove(
            pages_elements, page_height
        )

        for page_no, elements in pages_elements.items():
            if not elements:
                continue

            layout_type = self._column_detector.detect(elements, page_width)
            ordered = self._reading_order.reconstruct(
                elements, layout_type, page_width
            )
            enriched = self._enrich_tables(ordered)
            with_sections = self._section_builder.assign_section_titles(
                enriched
            )
            quality = self._quality_scorer.score_page(
                with_sections, page_height
            )
            page_scores.append(quality)

            doc = self._elements_to_document(
                elements=with_sections,
                page_no=page_no,
                total_pages=total_pages,
                filename=filename,
                user_id=user_id,
                document_id=document_id,
                quality=quality,
                layout_type=layout_type,
            )
            all_documents.append(doc)

        aggregate = self._aggregate_quality(page_scores)
        return all_documents, aggregate

    def _enrich_tables(
        self, elements: list[DocumentElement]
    ) -> list[DocumentElement]:
        result: list[DocumentElement] = []
        for elem in elements:
            if elem.block_type == "table":
                table_result = self._table_handler.process_table_element(
                    elem, ""
                )
                for sentence in table_result.semantic_sentences:
                    result.append(DocumentElement(
                        page_no=elem.page_no,
                        text=sentence,
                        bbox=elem.bbox,
                        block_type="paragraph",
                        section_title=elem.section_title,
                        reading_order=elem.reading_order,
                        confidence=0.9,
                    ))
            result.append(elem)
        return result

    def _elements_to_document(
        self,
        elements: list[DocumentElement],
        page_no: int,
        total_pages: int,
        filename: str,
        user_id: str,
        document_id: str,
        quality: ParseQualityScore,
        layout_type: LayoutType,
    ) -> Document:
        text_parts: list[str] = []
        for elem in elements:
            if elem.block_type == "table":
                text_parts.append(f"\n{elem.text}\n")
            else:
                text_parts.append(elem.text)

        page_content = "\n".join(text_parts)
        section_title = next(
            (e.section_title for e in elements if e.section_title), ""
        )
        has_table = any(e.block_type == "table" for e in elements)

        metadata = DocumentMetadata(
            filename=filename,
            user_id=user_id,
            page=page_no,
            total_pages=total_pages,
            parser="pymupdf_layout",
            document_id=document_id,
        )

        meta_dict = metadata.to_dict()
        meta_dict["section_title"] = section_title
        meta_dict["has_table"] = has_table
        meta_dict["quality_score"] = quality.score
        meta_dict["quality_issues"] = list(quality.issues)
        meta_dict["layout_type"] = layout_type.value
        meta_dict["block_types"] = list(
            set(e.block_type for e in elements)
        )

        return Document(page_content=page_content, metadata=meta_dict)

    def _aggregate_quality(
        self, page_scores: list[ParseQualityScore]
    ) -> ParseQualityScore:
        if not page_scores:
            return ParseQualityScore(
                page=0, score=0.0, text_char_count=0,
                avg_word_length=0.0, order_consistency=1.0,
                issues=("no_pages",),
            )

        avg_score = sum(s.score for s in page_scores) / len(page_scores)
        total_chars = sum(s.text_char_count for s in page_scores)
        avg_word_len = (
            sum(s.avg_word_length for s in page_scores) / len(page_scores)
        )
        avg_order = (
            sum(s.order_consistency for s in page_scores) / len(page_scores)
        )
        all_issues: set[str] = set()
        for s in page_scores:
            all_issues.update(s.issues)

        return ParseQualityScore(
            page=0,
            score=round(avg_score, 3),
            text_char_count=total_chars,
            avg_word_length=round(avg_word_len, 2),
            order_consistency=round(avg_order, 3),
            issues=tuple(sorted(all_issues)),
        )
