"""LLMFactory: Anthropic 모델별 temperature 전달 여부 검증.

최신 Claude 모델은 temperature를 400으로 거부하므로 보내지 않고,
구형 모델에는 기존처럼 요청한 temperature를 보낸다.
"""
import os
from datetime import datetime, timezone
from unittest.mock import patch

from src.domain.llm_model.entity import LlmModel
from src.infrastructure.llm.llm_factory import LLMFactory


def _anthropic_model(model_name: str, max_output_tokens: int | None = None) -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="m-1",
        provider="anthropic",
        model_name=model_name,
        display_name=model_name,
        description=None,
        api_key_env="ANTHROPIC_API_KEY",
        max_tokens=None,
        is_active=True,
        is_default=False,
        created_at=now,
        updated_at=now,
        max_output_tokens=max_output_tokens,
    )


def _create(model_name: str, temperature: float):
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        return LLMFactory().create(_anthropic_model(model_name), temperature=temperature)


def test_new_model_omits_temperature():
    chat = _create("claude-opus-5-5", 0.0)
    assert chat.temperature is None
    assert "temperature" not in chat._get_request_payload("hi")


def test_legacy_model_keeps_temperature():
    chat = _create("claude-sonnet-4-5-20250929", 0.3)
    assert chat.temperature == 0.3
    assert chat._get_request_payload("hi")["temperature"] == 0.3


def test_forced_tool_rejecting_model_gets_json_schema_subclass():  # F1 (M3 부분)
    from src.infrastructure.llm.structured_chat_anthropic import (
        JsonSchemaStructuredChatAnthropic,
    )

    assert isinstance(_create("claude-opus-5-5", 0.0), JsonSchemaStructuredChatAnthropic)


def test_legacy_model_keeps_plain_chat_anthropic():  # F2 (M3 부분)
    from langchain_anthropic import ChatAnthropic

    assert type(_create("claude-sonnet-4-6", 0.0)) is ChatAnthropic


# ── claude-agent-e2e-fixes Design §5.1 (F1~F4): 출력 한도 전달 ──────────────

def test_anthropic_null_sends_default_16000():  # F1·F2
    assert _create("claude-opus-5-5", 0.0)._get_request_payload("hi")["max_tokens"] == 16000
    assert _create("claude-sonnet-4-6", 0.0)._get_request_payload("hi")["max_tokens"] == 16000


def test_anthropic_stored_value_sent():  # F3
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        chat = LLMFactory().create(_anthropic_model("claude-opus-5-5", 64000), temperature=0.0)
    assert chat._get_request_payload("hi")["max_tokens"] == 64000


def test_factory_default_is_injectable():
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        chat = LLMFactory(anthropic_default_max_output_tokens=8000).create(
            _anthropic_model("claude-opus-5-5"), temperature=0.0,
        )
    assert chat._get_request_payload("hi")["max_tokens"] == 8000


def _openai_model(max_output_tokens: int | None) -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="o-1", provider="openai", model_name="gpt-4o", display_name="gpt",
        description=None, api_key_env="OPENAI_API_KEY", max_tokens=None,
        is_active=True, is_default=False, created_at=now, updated_at=now,
        max_output_tokens=max_output_tokens,
    )


def test_openai_max_tokens_only_when_stored():  # F4
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        plain = LLMFactory().create(_openai_model(None), temperature=0.0)
        capped = LLMFactory().create(_openai_model(2000), temperature=0.0)
    assert plain.max_tokens is None
    assert capped.max_tokens == 2000
