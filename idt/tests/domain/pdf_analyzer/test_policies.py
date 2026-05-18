import pytest

from src.domain.pdf_analyzer.policies import ClassificationPolicy
from src.domain.pdf_analyzer.schemas import (
    PDFDocumentType,
    PageFeatures,
    SummaryMetrics,
)
from src.domain.pdf_analyzer.value_objects import AnalysisConfig


def _make_features(
    count: int = 5,
    text_char_count: int = 2000,
    image_count: int = 0,
    image_area_ratio: float = 0.0,
    table_count: int = 0,
    has_extractable_text: bool = True,
) -> list:
    return [
        PageFeatures(
            page_number=i,
            text_char_count=text_char_count,
            image_count=image_count,
            image_area_ratio=image_area_ratio,
            table_count=table_count,
            has_extractable_text=has_extractable_text,
        )
        for i in range(1, count + 1)
    ]


class TestComputeSummary:
    def test_basic(self):
        features = [
            PageFeatures(
                page_number=1, text_char_count=100, image_count=2,
                image_area_ratio=0.3, table_count=1, has_extractable_text=True,
            ),
            PageFeatures(
                page_number=2, text_char_count=200, image_count=0,
                image_area_ratio=0.1, table_count=0, has_extractable_text=True,
            ),
        ]
        summary = ClassificationPolicy.compute_summary(features)
        assert summary.avg_text_chars == 150.0
        assert summary.avg_image_count == 1.0
        assert summary.avg_image_area_ratio == pytest.approx(0.2)
        assert summary.avg_table_count == 0.5
        assert summary.extractable_text_ratio == 1.0

    def test_empty_features(self):
        summary = ClassificationPolicy.compute_summary([])
        assert summary.avg_text_chars == 0.0
        assert summary.extractable_text_ratio == 0.0

    def test_partial_extractable(self):
        features = [
            PageFeatures(
                page_number=1, text_char_count=100, image_count=0,
                image_area_ratio=0.0, table_count=0, has_extractable_text=True,
            ),
            PageFeatures(
                page_number=2, text_char_count=10, image_count=0,
                image_area_ratio=0.0, table_count=0, has_extractable_text=False,
            ),
        ]
        summary = ClassificationPolicy.compute_summary(features)
        assert summary.extractable_text_ratio == 0.5


class TestClassify:
    def test_text_heavy(self):
        features = _make_features(
            text_char_count=2000, has_extractable_text=True,
        )
        summary = ClassificationPolicy.compute_summary(features)
        doc_type, conf = ClassificationPolicy.classify(
            features, summary, AnalysisConfig(),
        )
        assert doc_type == PDFDocumentType.TEXT_HEAVY
        assert conf > 0.5

    def test_ocr_heavy(self):
        features = _make_features(
            text_char_count=10, image_count=1,
            image_area_ratio=0.9, has_extractable_text=False,
        )
        summary = ClassificationPolicy.compute_summary(features)
        doc_type, conf = ClassificationPolicy.classify(
            features, summary, AnalysisConfig(),
        )
        assert doc_type == PDFDocumentType.OCR_HEAVY
        assert conf > 0.5

    def test_ocr_heavy_boundary(self):
        # 5페이지 중 1페이지만 추출 가능 = ratio 0.2 < 0.3
        features = _make_features(count=5, has_extractable_text=False)
        features[0] = PageFeatures(
            page_number=1, text_char_count=100, image_count=0,
            image_area_ratio=0.0, table_count=0, has_extractable_text=True,
        )
        summary = ClassificationPolicy.compute_summary(features)
        doc_type, _ = ClassificationPolicy.classify(
            features, summary, AnalysisConfig(),
        )
        assert doc_type == PDFDocumentType.OCR_HEAVY

    def test_table_heavy(self):
        features = _make_features(
            text_char_count=500, table_count=3, has_extractable_text=True,
        )
        summary = ClassificationPolicy.compute_summary(features)
        doc_type, conf = ClassificationPolicy.classify(
            features, summary, AnalysisConfig(),
        )
        assert doc_type == PDFDocumentType.TABLE_HEAVY
        assert conf > 0.0

    def test_multimodal_image_and_table(self):
        features = _make_features(
            text_char_count=300, image_count=2,
            image_area_ratio=0.5, table_count=1, has_extractable_text=True,
        )
        summary = ClassificationPolicy.compute_summary(features)
        doc_type, conf = ClassificationPolicy.classify(
            features, summary, AnalysisConfig(),
        )
        assert doc_type == PDFDocumentType.MULTIMODAL

    def test_multimodal_image_only(self):
        features = _make_features(
            text_char_count=300, image_count=3,
            image_area_ratio=0.6, table_count=0, has_extractable_text=True,
        )
        summary = ClassificationPolicy.compute_summary(features)
        doc_type, _ = ClassificationPolicy.classify(
            features, summary, AnalysisConfig(),
        )
        assert doc_type == PDFDocumentType.MULTIMODAL

    def test_empty_features_returns_text_heavy(self):
        summary = SummaryMetrics(
            avg_text_chars=0.0, avg_image_count=0.0,
            avg_image_area_ratio=0.0, avg_table_count=0.0,
            extractable_text_ratio=0.0,
        )
        doc_type, conf = ClassificationPolicy.classify(
            [], summary, AnalysisConfig(),
        )
        assert doc_type == PDFDocumentType.TEXT_HEAVY
        assert conf == 0.0

    def test_custom_config_lower_table_threshold(self):
        config = AnalysisConfig(table_avg_threshold=1.0)
        features = _make_features(
            text_char_count=500, table_count=1, has_extractable_text=True,
        )
        summary = ClassificationPolicy.compute_summary(features)
        doc_type, _ = ClassificationPolicy.classify(features, summary, config)
        assert doc_type == PDFDocumentType.TABLE_HEAVY

    def test_ocr_priority_over_table(self):
        features = _make_features(
            text_char_count=10, table_count=5,
            has_extractable_text=False,
        )
        summary = ClassificationPolicy.compute_summary(features)
        doc_type, _ = ClassificationPolicy.classify(
            features, summary, AnalysisConfig(),
        )
        assert doc_type == PDFDocumentType.OCR_HEAVY

    def test_confidence_range(self):
        for doc_type_features in [
            _make_features(text_char_count=2000, has_extractable_text=True),
            _make_features(text_char_count=10, has_extractable_text=False),
            _make_features(table_count=3, has_extractable_text=True),
            _make_features(image_area_ratio=0.6, has_extractable_text=True),
        ]:
            summary = ClassificationPolicy.compute_summary(doc_type_features)
            _, conf = ClassificationPolicy.classify(
                doc_type_features, summary, AnalysisConfig(),
            )
            assert 0.0 <= conf <= 1.0
