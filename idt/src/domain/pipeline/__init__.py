"""Pipeline domain module."""
from src.domain.pipeline.enums.document_category import DocumentCategory
from src.domain.pipeline.config.chunking_strategy_config import (
    CATEGORY_CHUNKING_CONFIG,
    get_chunking_config,
)
from src.domain.pipeline.state.pipeline_state import PipelineState
from src.domain.pipeline.schemas.classification_schema import ClassificationResult
from src.domain.pipeline.schemas.upload_schema import DocumentUploadResponse

__all__ = [
    "DocumentCategory",
    "CATEGORY_CHUNKING_CONFIG",
    "get_chunking_config",
    "PipelineState",
    "ClassificationResult",
    "DocumentUploadResponse",
]
