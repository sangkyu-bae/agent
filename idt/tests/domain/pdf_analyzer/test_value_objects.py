import pytest

from src.domain.pdf_analyzer.value_objects import AnalysisConfig


class TestAnalysisConfig:
    def test_defaults(self):
        config = AnalysisConfig()
        assert config.sample_pages == 5
        assert config.min_text_threshold == 50
        assert config.ocr_text_ratio_threshold == 0.3
        assert config.table_avg_threshold == 2.0
        assert config.image_area_threshold == 0.4
        assert config.image_only_threshold == 0.5

    def test_custom_values(self):
        config = AnalysisConfig(sample_pages=10, min_text_threshold=100)
        assert config.sample_pages == 10
        assert config.min_text_threshold == 100

    def test_frozen(self):
        config = AnalysisConfig()
        with pytest.raises(Exception):
            config.sample_pages = 10

    def test_sample_pages_zero_rejected(self):
        with pytest.raises(ValueError):
            AnalysisConfig(sample_pages=0)

    def test_sample_pages_negative_rejected(self):
        with pytest.raises(ValueError):
            AnalysisConfig(sample_pages=-1)

    def test_min_text_threshold_negative_rejected(self):
        with pytest.raises(ValueError):
            AnalysisConfig(min_text_threshold=-1)

    def test_ocr_threshold_out_of_range(self):
        with pytest.raises(ValueError):
            AnalysisConfig(ocr_text_ratio_threshold=1.5)

    def test_ocr_threshold_negative(self):
        with pytest.raises(ValueError):
            AnalysisConfig(ocr_text_ratio_threshold=-0.1)

    def test_image_area_threshold_out_of_range(self):
        with pytest.raises(ValueError):
            AnalysisConfig(image_area_threshold=1.1)

    def test_image_only_threshold_out_of_range(self):
        with pytest.raises(ValueError):
            AnalysisConfig(image_only_threshold=-0.1)

    def test_table_avg_threshold_negative(self):
        with pytest.raises(ValueError):
            AnalysisConfig(table_avg_threshold=-1.0)

    def test_boundary_values_accepted(self):
        config = AnalysisConfig(
            sample_pages=1,
            min_text_threshold=0,
            ocr_text_ratio_threshold=0.0,
            table_avg_threshold=0.0,
            image_area_threshold=1.0,
            image_only_threshold=1.0,
        )
        assert config.sample_pages == 1
        assert config.image_area_threshold == 1.0
