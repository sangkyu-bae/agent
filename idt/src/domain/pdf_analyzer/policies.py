from typing import List, Tuple

from src.domain.pdf_analyzer.schemas import (
    PDFDocumentType,
    PageFeatures,
    SummaryMetrics,
)
from src.domain.pdf_analyzer.value_objects import AnalysisConfig


class ClassificationPolicy:

    @staticmethod
    def classify(
        page_features: List[PageFeatures],
        summary: SummaryMetrics,
        config: AnalysisConfig,
    ) -> Tuple[PDFDocumentType, float]:
        if not page_features:
            return PDFDocumentType.TEXT_HEAVY, 0.0

        if summary.extractable_text_ratio < config.ocr_text_ratio_threshold:
            confidence = 1.0 - summary.extractable_text_ratio
            return PDFDocumentType.OCR_HEAVY, round(confidence, 2)

        if summary.avg_table_count >= config.table_avg_threshold:
            confidence = min(summary.avg_table_count / 5.0, 1.0)
            return PDFDocumentType.TABLE_HEAVY, round(confidence, 2)

        if (
            summary.avg_image_area_ratio > config.image_area_threshold
            and summary.avg_table_count >= 1.0
        ):
            confidence = (
                summary.avg_image_area_ratio * 0.6
                + min(summary.avg_table_count / 3.0, 1.0) * 0.4
            )
            return PDFDocumentType.MULTIMODAL, round(min(confidence, 1.0), 2)

        if summary.avg_image_area_ratio > config.image_only_threshold:
            confidence = summary.avg_image_area_ratio
            return PDFDocumentType.MULTIMODAL, round(confidence, 2)

        confidence = summary.extractable_text_ratio
        return PDFDocumentType.TEXT_HEAVY, round(confidence, 2)

    @staticmethod
    def compute_summary(page_features: List[PageFeatures]) -> SummaryMetrics:
        if not page_features:
            return SummaryMetrics(
                avg_text_chars=0.0,
                avg_image_count=0.0,
                avg_image_area_ratio=0.0,
                avg_table_count=0.0,
                extractable_text_ratio=0.0,
            )

        n = len(page_features)
        return SummaryMetrics(
            avg_text_chars=sum(p.text_char_count for p in page_features) / n,
            avg_image_count=sum(p.image_count for p in page_features) / n,
            avg_image_area_ratio=sum(p.image_area_ratio for p in page_features) / n,
            avg_table_count=sum(p.table_count for p in page_features) / n,
            extractable_text_ratio=sum(
                1 for p in page_features if p.has_extractable_text
            ) / n,
        )
