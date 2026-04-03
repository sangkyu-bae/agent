"""Domain schemas for HTML to PDF conversion.

No external API calls or LangChain usage allowed in domain layer.
"""
from typing import Optional

from pydantic import BaseModel, field_validator


class HtmlToPdfRequest(BaseModel):
    """HTML → PDF 변환 요청."""

    html_content: str
    filename: str
    request_id: str
    user_id: str
    css_content: Optional[str] = None
    base_url: Optional[str] = None

    @field_validator("html_content")
    @classmethod
    def html_content_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("html_content must not be empty")
        return v

    @field_validator("filename")
    @classmethod
    def filename_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("filename must not be empty")
        if not v.endswith(".pdf"):
            return v + ".pdf"
        return v


class HtmlToPdfResult(BaseModel):
    """HTML → PDF 변환 결과."""

    filename: str
    user_id: str
    request_id: str
    pdf_bytes: bytes
    size_bytes: int
    converter_used: str
