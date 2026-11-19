"""LLMFactory: Anthropic 모델별 temperature 전달 여부 검증.

최신 Claude 모델은 temperature를 400으로 거부하므로 보내지 않고,
구형 모델에는 기존처럼 요청한 temperature를 보낸다.
"""
import os
from datetime import datetime, timezone
from unittest.mock import patch

from src.domain.llm_model.entity import LlmModel
from src.infrastructure.llm.llm_factory import LLMFactory


def _anthropic_model(model_name: str) -> LlmModel:
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
