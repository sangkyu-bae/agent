"""Domain schema tests for general_chat — mock 금지."""
import pytest
from pydantic import ValidationError

from src.domain.general_chat.schemas import (
    DocumentSource,
    GeneralChatRequest,
    GeneralChatResponse,
    ToolUsageRecord,
)


def test_general_chat_request_defaults():
    """TC-1: GeneralChatRequest 기본값 — top_k=5, session_id=None."""
    req = GeneralChatRequest(user_id="u1", message="hello")
    assert req.top_k == 5
    assert req.session_id is None


def test_general_chat_request_missing_required_fields():
    """TC-2: 필수 필드 누락 시 ValidationError."""
    with pytest.raises(ValidationError):
        GeneralChatRequest(user_id="u1")  # message 누락


def test_document_source_field_types():
    """TC-3: DocumentSource 필드 타입 — score는 float."""
    src = DocumentSource(content="텍스트", source="file.pdf", chunk_id="c1", score=0.95)
    assert isinstance(src.score, float)
    assert src.content == "텍스트"


def test_general_chat_response_serialization():
    """TC-4: GeneralChatResponse JSON 직렬화 정상."""
    resp = GeneralChatResponse(
        user_id="u1",
        session_id="s1",
        answer="답변",
        tools_used=["tavily_search"],
        sources=[],
        was_summarized=False,
        request_id="req-1",
    )
    data = resp.model_dump()
    assert data["answer"] == "답변"
    assert data["tools_used"] == ["tavily_search"]
    assert data["was_summarized"] is False


def test_tool_usage_record_empty_dict():
    """TC-5: ToolUsageRecord — tool_input={}(빈 dict) 허용."""
    record = ToolUsageRecord(tool_name="some_tool", tool_input={}, tool_output="결과")
    assert record.tool_input == {}


def test_general_chat_response_empty_tools_used():
    """TC-6: GeneralChatResponse — tools_used 빈 리스트 허용."""
    resp = GeneralChatResponse(
        user_id="u1",
        session_id="s1",
        answer="답변",
        tools_used=[],
        sources=[],
        was_summarized=False,
        request_id="req-1",
    )
    assert resp.tools_used == []
