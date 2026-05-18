from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisConfig:
    sample_pages: int = 5
    min_text_threshold: int = 50
    ocr_text_ratio_threshold: float = 0.3
    table_avg_threshold: float = 2.0
    image_area_threshold: float = 0.4
    image_only_threshold: float = 0.5

    def __post_init__(self) -> None:
        if self.sample_pages < 1:
            raise ValueError("sample_pages must be >= 1")
        if self.min_text_threshold < 0:
            raise ValueError("min_text_threshold must be >= 0")
        if not (0.0 <= self.ocr_text_ratio_threshold <= 1.0):
            raise ValueError("ocr_text_ratio_threshold must be 0.0~1.0")
        if self.table_avg_threshold < 0.0:
            raise ValueError("table_avg_threshold must be >= 0.0")
        if not (0.0 <= self.image_area_threshold <= 1.0):
            raise ValueError("image_area_threshold must be 0.0~1.0")
        if not (0.0 <= self.image_only_threshold <= 1.0):
            raise ValueError("image_only_threshold must be 0.0~1.0")
