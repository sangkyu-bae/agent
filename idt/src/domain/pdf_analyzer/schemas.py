from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class PDFDocumentType(str, Enum):
    TEXT_HEAVY = "text_heavy"
    OCR_HEAVY = "ocr_heavy"
    TABLE_HEAVY = "table_heavy"
    MULTIMODAL = "multimodal"


class PageFeatures(BaseModel):
    page_number: int = Field(ge=1)
    text_char_count: int = Field(ge=0)
    image_count: int = Field(ge=0)
    image_area_ratio: float = Field(ge=0.0, le=1.0)
    table_count: int = Field(ge=0)
    has_extractable_text: bool

    model_config = {"frozen": True}


class SummaryMetrics(BaseModel):
    avg_text_chars: float = Field(ge=0.0)
    avg_image_count: float = Field(ge=0.0)
    avg_image_area_ratio: float = Field(ge=0.0, le=1.0)
    avg_table_count: float = Field(ge=0.0)
    extractable_text_ratio: float = Field(ge=0.0, le=1.0)

    model_config = {"frozen": True}


class AnalysisResult(BaseModel):
    document_type: PDFDocumentType
    confidence: float = Field(ge=0.0, le=1.0)
    total_pages: int = Field(ge=1)
    sampled_pages: int = Field(ge=1)
    page_features: List[PageFeatures]
    summary_metrics: SummaryMetrics

    model_config = {"frozen": True}
