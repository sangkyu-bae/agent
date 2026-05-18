from typing import List, Optional

import fitz

from src.domain.pdf_analyzer.interfaces import PDFAnalyzerInterface
from src.domain.pdf_analyzer.policies import ClassificationPolicy
from src.domain.pdf_analyzer.schemas import AnalysisResult, PageFeatures
from src.domain.pdf_analyzer.value_objects import AnalysisConfig


class PyMuPDFAnalyzer(PDFAnalyzerInterface):

    def analyze_bytes(
        self,
        file_bytes: bytes,
        config: Optional[AnalysisConfig] = None,
    ) -> AnalysisResult:
        config = config or AnalysisConfig()
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            return self._analyze_document(doc, config)

    def analyze_path(
        self,
        file_path: str,
        config: Optional[AnalysisConfig] = None,
    ) -> AnalysisResult:
        config = config or AnalysisConfig()
        with fitz.open(file_path) as doc:
            return self._analyze_document(doc, config)

    def _analyze_document(
        self,
        doc: fitz.Document,
        config: AnalysisConfig,
    ) -> AnalysisResult:
        total_pages = doc.page_count
        sample_count = min(config.sample_pages, total_pages)

        page_features: List[PageFeatures] = []
        for page_idx in range(sample_count):
            page = doc[page_idx]
            features = self._extract_page_features(page, page_idx + 1, config)
            page_features.append(features)

        summary = ClassificationPolicy.compute_summary(page_features)
        document_type, confidence = ClassificationPolicy.classify(
            page_features, summary, config,
        )

        return AnalysisResult(
            document_type=document_type,
            confidence=confidence,
            total_pages=total_pages,
            sampled_pages=sample_count,
            page_features=page_features,
            summary_metrics=summary,
        )

    def _extract_page_features(
        self,
        page: fitz.Page,
        page_number: int,
        config: AnalysisConfig,
    ) -> PageFeatures:
        text = page.get_text()
        text_char_count = len(text.strip())

        images = page.get_images(full=True)
        image_count = len(images)
        image_area_ratio = self._compute_image_area_ratio(page, images)

        table_count = self._count_tables(page)

        has_extractable_text = text_char_count >= config.min_text_threshold

        return PageFeatures(
            page_number=page_number,
            text_char_count=text_char_count,
            image_count=image_count,
            image_area_ratio=round(image_area_ratio, 4),
            table_count=table_count,
            has_extractable_text=has_extractable_text,
        )

    def _compute_image_area_ratio(
        self,
        page: fitz.Page,
        images: list,
    ) -> float:
        if not images:
            return 0.0

        page_rect = page.rect
        page_area = page_rect.width * page_rect.height
        if page_area <= 0:
            return 0.0

        total_image_area = 0.0
        for img in images:
            xref = img[0]
            try:
                img_rects = page.get_image_rects(xref)
                for rect in img_rects:
                    total_image_area += rect.width * rect.height
            except Exception:
                pass

        ratio = total_image_area / page_area
        return min(ratio, 1.0)

    def _count_tables(self, page: fitz.Page) -> int:
        try:
            tables = page.find_tables()
            return len(tables.tables)
        except Exception:
            return 0
