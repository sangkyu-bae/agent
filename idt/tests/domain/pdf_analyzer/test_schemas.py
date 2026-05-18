import pytest

from src.domain.pdf_analyzer.schemas import (
    AnalysisResult,
    PDFDocumentType,
    PageFeatures,
    SummaryMetrics,
)


class TestPDFDocumentType:
    def test_values(self):
        assert PDFDocumentType.TEXT_HEAVY.value == "text_heavy"
        assert PDFDocumentType.OCR_HEAVY.value == "ocr_heavy"
        assert PDFDocumentType.TABLE_HEAVY.value == "table_heavy"
        assert PDFDocumentType.MULTIMODAL.value == "multimodal"

    def test_from_string(self):
        assert PDFDocumentType("text_heavy") == PDFDocumentType.TEXT_HEAVY

    def test_member_count(self):
        assert len(PDFDocumentType) == 4


class TestPageFeatures:
    def test_valid_construction(self):
        pf = PageFeatures(
            page_number=1,
            text_char_count=500,
            image_count=2,
            image_area_ratio=0.3,
            table_count=1,
            has_extractable_text=True,
        )
        assert pf.page_number == 1
        assert pf.text_char_count == 500
        assert pf.image_area_ratio == 0.3

    def test_page_number_must_be_positive(self):
        with pytest.raises(Exception):
            PageFeatures(
                page_number=0,
                text_char_count=0,
                image_count=0,
                image_area_ratio=0.0,
                table_count=0,
                has_extractable_text=False,
            )

    def test_image_area_ratio_max(self):
        with pytest.raises(Exception):
            PageFeatures(
                page_number=1,
                text_char_count=0,
                image_count=0,
                image_area_ratio=1.5,
                table_count=0,
                has_extractable_text=False,
            )

    def test_negative_text_char_count_rejected(self):
        with pytest.raises(Exception):
            PageFeatures(
                page_number=1,
                text_char_count=-1,
                image_count=0,
                image_area_ratio=0.0,
                table_count=0,
                has_extractable_text=False,
            )

    def test_frozen(self):
        pf = PageFeatures(
            page_number=1,
            text_char_count=100,
            image_count=0,
            image_area_ratio=0.0,
            table_count=0,
            has_extractable_text=True,
        )
        with pytest.raises(Exception):
            pf.page_number = 2


class TestSummaryMetrics:
    def test_valid_construction(self):
        sm = SummaryMetrics(
            avg_text_chars=1500.0,
            avg_image_count=1.0,
            avg_image_area_ratio=0.2,
            avg_table_count=0.5,
            extractable_text_ratio=0.8,
        )
        assert sm.avg_text_chars == 1500.0
        assert sm.extractable_text_ratio == 0.8

    def test_ratio_bounds(self):
        with pytest.raises(Exception):
            SummaryMetrics(
                avg_text_chars=0.0,
                avg_image_count=0.0,
                avg_image_area_ratio=1.5,
                avg_table_count=0.0,
                extractable_text_ratio=0.0,
            )


class TestAnalysisResult:
    def _make_page_features(self, n: int = 3):
        return [
            PageFeatures(
                page_number=i,
                text_char_count=100 * i,
                image_count=0,
                image_area_ratio=0.0,
                table_count=0,
                has_extractable_text=True,
            )
            for i in range(1, n + 1)
        ]

    def test_valid_construction(self):
        result = AnalysisResult(
            document_type=PDFDocumentType.TEXT_HEAVY,
            confidence=0.95,
            total_pages=10,
            sampled_pages=3,
            page_features=self._make_page_features(3),
            summary_metrics=SummaryMetrics(
                avg_text_chars=200.0,
                avg_image_count=0.0,
                avg_image_area_ratio=0.0,
                avg_table_count=0.0,
                extractable_text_ratio=1.0,
            ),
        )
        assert result.document_type == PDFDocumentType.TEXT_HEAVY
        assert result.confidence == 0.95
        assert result.total_pages == 10
        assert result.sampled_pages == 3
        assert len(result.page_features) == 3

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            AnalysisResult(
                document_type=PDFDocumentType.TEXT_HEAVY,
                confidence=1.5,
                total_pages=1,
                sampled_pages=1,
                page_features=self._make_page_features(1),
                summary_metrics=SummaryMetrics(
                    avg_text_chars=0.0,
                    avg_image_count=0.0,
                    avg_image_area_ratio=0.0,
                    avg_table_count=0.0,
                    extractable_text_ratio=0.0,
                ),
            )
