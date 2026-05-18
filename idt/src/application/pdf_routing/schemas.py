from typing import Optional

from pydantic import BaseModel, field_validator


class RoutePDFRequest(BaseModel):
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


class RoutePDFResponse(BaseModel):
    parser_type: str
    document_type: Optional[str] = None
    confidence: float
    reason: str
    is_fallback: bool
    analysis_summary: Optional[dict] = None
    request_id: str
