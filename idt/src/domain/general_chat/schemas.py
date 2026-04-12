"""General Chat API 도메인 스키마 (Pydantic BaseModel)."""
from __future__ import annotations

from pydantic import BaseModel


class ToolUsageRecord(BaseModel):
    """에이전트가 호출한 단일 도구 사용 기록."""

    tool_name: str
    tool_input: dict
    tool_output: str


class DocumentSource(BaseModel):
    """내부 문서 검색 결과 출처 정보."""

    content: str
    source: str
    chunk_id: str
    score: float


class GeneralChatRequest(BaseModel):
    """POST /api/v1/chat 요청 스키마."""

    user_id: str
    session_id: str | None = None  # None이면 서버에서 UUID 신규 발급
    message: str
    top_k: int = 5


class GeneralChatResponse(BaseModel):
    """POST /api/v1/chat 응답 스키마."""

    user_id: str
    session_id: str
    answer: str
    tools_used: list[str]
    sources: list[DocumentSource]
    was_summarized: bool
    request_id: str
