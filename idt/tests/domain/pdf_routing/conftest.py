from src.domain.pdf_analyzer.schemas import (
    AnalysisResult,
    PageFeatures,
    PDFDocumentType,
    SummaryMetrics,
)


def make_analysis_result(
    document_type: PDFDocumentType = PDFDocumentType.TEXT_HEAVY,
    confidence: float = 0.8,
    total_pages: int = 10,
    sampled_pages: int = 5,
) -> AnalysisResult:
    page_features = [
        PageFeatures(
            page_number=i + 1,
            text_char_count=500,
            image_count=0,
            image_area_ratio=0.0,
            table_count=0,
            has_extractable_text=True,
        )
        for i in range(sampled_pages)
    ]
    summary = SummaryMetrics(
        avg_text_chars=500.0,
        avg_image_count=0.0,
        avg_image_area_ratio=0.0,
        avg_table_count=0.0,
        extractable_text_ratio=1.0,
    )
    return AnalysisResult(
        document_type=document_type,
        confidence=confidence,
        total_pages=total_pages,
        sampled_pages=sampled_pages,
        page_features=page_features,
        summary_metrics=summary,
    )
