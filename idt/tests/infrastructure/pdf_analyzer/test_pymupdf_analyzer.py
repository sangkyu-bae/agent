import pytest
import fitz

from src.domain.pdf_analyzer.schemas import PDFDocumentType
from src.domain.pdf_analyzer.value_objects import AnalysisConfig
from src.infrastructure.pdf_analyzer.pymupdf_analyzer import PyMuPDFAnalyzer


def _create_text_pdf(pages: int = 5) -> bytes:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i + 1} " + "Sample text content " * 30)
    data = doc.tobytes()
    doc.close()
    return data


def _create_image_only_pdf(pages: int = 5) -> bytes:
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page()
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 200), 1)
        pix.set_rect(pix.irect, (255, 0, 0, 255))
        page.insert_image(page.rect, pixmap=pix)
    data = doc.tobytes()
    doc.close()
    return data


class TestPyMuPDFAnalyzer:
    def test_analyze_text_pdf(self):
        analyzer = PyMuPDFAnalyzer()
        pdf_bytes = _create_text_pdf()
        result = analyzer.analyze_bytes(pdf_bytes)
        assert result.document_type == PDFDocumentType.TEXT_HEAVY
        assert result.sampled_pages == 5
        assert result.total_pages == 5
        assert result.confidence > 0.0
        assert len(result.page_features) == 5

    def test_analyze_image_only_pdf(self):
        analyzer = PyMuPDFAnalyzer()
        pdf_bytes = _create_image_only_pdf()
        result = analyzer.analyze_bytes(pdf_bytes)
        assert result.document_type == PDFDocumentType.OCR_HEAVY

    def test_sample_pages_limit(self):
        analyzer = PyMuPDFAnalyzer()
        pdf_bytes = _create_text_pdf(pages=10)
        config = AnalysisConfig(sample_pages=3)
        result = analyzer.analyze_bytes(pdf_bytes, config=config)
        assert result.sampled_pages == 3
        assert result.total_pages == 10
        assert len(result.page_features) == 3

    def test_short_pdf_analyzes_all(self):
        analyzer = PyMuPDFAnalyzer()
        pdf_bytes = _create_text_pdf(pages=2)
        result = analyzer.analyze_bytes(pdf_bytes)
        assert result.sampled_pages == 2
        assert result.total_pages == 2

    def test_analyze_from_path(self, tmp_path):
        pdf_bytes = _create_text_pdf()
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(pdf_bytes)
        analyzer = PyMuPDFAnalyzer()
        result = analyzer.analyze_path(str(pdf_file))
        assert result.document_type == PDFDocumentType.TEXT_HEAVY

    def test_page_features_fields(self):
        analyzer = PyMuPDFAnalyzer()
        pdf_bytes = _create_text_pdf(pages=1)
        config = AnalysisConfig(sample_pages=1)
        result = analyzer.analyze_bytes(pdf_bytes, config=config)
        pf = result.page_features[0]
        assert pf.page_number == 1
        assert pf.text_char_count > 0
        assert pf.has_extractable_text is True
        assert 0.0 <= pf.image_area_ratio <= 1.0
        assert pf.image_count >= 0
        assert pf.table_count >= 0

    def test_summary_metrics_populated(self):
        analyzer = PyMuPDFAnalyzer()
        pdf_bytes = _create_text_pdf()
        result = analyzer.analyze_bytes(pdf_bytes)
        sm = result.summary_metrics
        assert sm.avg_text_chars > 0.0
        assert sm.extractable_text_ratio > 0.0
        assert 0.0 <= sm.avg_image_area_ratio <= 1.0

    def test_single_page_pdf(self):
        analyzer = PyMuPDFAnalyzer()
        pdf_bytes = _create_text_pdf(pages=1)
        result = analyzer.analyze_bytes(pdf_bytes)
        assert result.total_pages == 1
        assert result.sampled_pages == 1

    def test_custom_config_applied(self):
        analyzer = PyMuPDFAnalyzer()
        pdf_bytes = _create_text_pdf(pages=8)
        config = AnalysisConfig(sample_pages=2, min_text_threshold=10000)
        result = analyzer.analyze_bytes(pdf_bytes, config=config)
        assert result.sampled_pages == 2
        for pf in result.page_features:
            assert pf.has_extractable_text is False
