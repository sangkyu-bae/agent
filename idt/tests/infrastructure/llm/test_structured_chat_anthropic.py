"""JsonSchemaStructuredChatAnthropic — 강제 tool_choice 거부 모델용 (claude-agent-e2e-fixes §5.2).

2026-11-19 실호출: claude-opus-5-5 는 function_calling(강제 tool_choice) 400,
json_schema 정상. 하위 클래스는 기본 method 만 바꾼다(F5·F6).
"""
from unittest.mock import MagicMock, patch

from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel

from src.application.pii_masking.guarded_llm import GuardedLlm
from src.infrastructure.llm.structured_chat_anthropic import (
    JsonSchemaStructuredChatAnthropic,
)


class _Schema(BaseModel):
    next: str


def _model() -> JsonSchemaStructuredChatAnthropic:
    return JsonSchemaStructuredChatAnthropic(model="claude-opus-5-5", api_key="x")


def test_is_chat_anthropic_subclass():
    assert isinstance(_model(), ChatAnthropic)


def test_default_method_is_json_schema():  # F5
    with patch.object(ChatAnthropic, "with_structured_output", return_value="r") as parent:
        assert _model().with_structured_output(_Schema) == "r"
    assert parent.call_args.kwargs["method"] == "json_schema"


def test_explicit_method_respected():  # F5
    with patch.object(ChatAnthropic, "with_structured_output", return_value="r") as parent:
        _model().with_structured_output(_Schema, method="function_calling", include_raw=True)
    assert parent.call_args.kwargs["method"] == "function_calling"
    assert parent.call_args.kwargs["include_raw"] is True


def test_guarded_proxy_delegates_to_json_schema():  # F6 / FR-10
    with patch.object(ChatAnthropic, "with_structured_output", return_value=MagicMock()) as parent:
        GuardedLlm(inner=_model(), masker=MagicMock()).with_structured_output(_Schema)
    assert parent.call_args.kwargs["method"] == "json_schema"
