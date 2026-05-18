from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class AdvancedIngestRequest(BaseModel):
    filename: str
    user_id: str
    request_id: str
    file_bytes: bytes
    collection_name: str = "documents"
    chunking_strategy: str = "parent_child"
    chunk_size: int = Field(default=500, ge=100, le=8000)
    chunk_overlap: int = Field(default=50, ge=0, le=500)
    enable_layout_analysis: bool = True
    enable_table_flattening: bool = True
    sample_pages: int = Field(default=3, ge=1, le=10)

    @field_validator("filename")
    @classmethod
    def filename_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("filename cannot be empty")
        return v

    @field_validator("user_id")
    @classmethod
    def user_id_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("user_id cannot be empty")
        return v

    model_config = {"arbitrary_types_allowed": True}


class AdvancedIngestResult(BaseModel):
    document_id: str
    filename: str
    user_id: str
    total_pages: int

    document_type: Optional[str] = None
    analysis_confidence: float = 0.0
    routed_parser: str = ""

    layout_quality_score: Optional[float] = None
    layout_applied: bool = False
    table_count: int = 0
    table_flattened: bool = False

    chunk_count: int = 0
    chunking_strategy: str = ""
    qdrant_indexed: int = 0
    es_indexed: int = 0

    processing_time_ms: int = 0
    step_timings: Dict[str, int] = Field(default_factory=dict)

    collection_name: str = ""
    request_id: str = ""
    errors: List[str] = Field(default_factory=list)
