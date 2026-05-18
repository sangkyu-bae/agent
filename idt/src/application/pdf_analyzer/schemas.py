from typing import Optional

from pydantic import BaseModel, field_validator


class AnalyzePDFRequest(BaseModel):
    filename: str
    user_id: str
    request_id: str
    file_bytes: Optional[bytes] = None
    file_path: Optional[str] = None
    sample_pages: Optional[int] = None

    @field_validator("filename")
    @classmethod
    def filename_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("filename cannot be empty")
        return v

    @field_validator("user_id")
    @classmethod
    def user_id_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("user_id cannot be empty")
        return v

    @field_validator("request_id")
    @classmethod
    def request_id_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("request_id cannot be empty")
        return v

    model_config = {"arbitrary_types_allowed": True}


class AnalyzePDFResponse(BaseModel):
    document_type: str
    confidence: float
    total_pages: int
    sampled_pages: int
    avg_text_chars: float
    avg_image_count: float
    avg_image_area_ratio: float
    avg_table_count: float
    extractable_text_ratio: float
    request_id: str
