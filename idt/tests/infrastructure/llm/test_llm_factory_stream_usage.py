"""LLMFactory: AGENT-OBS-001 §14-3 stream_usage=True 검증."""
import os
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from src.domain.llm_model.entity import LlmModel
from src.infrastructure.llm.llm_factory import LLMFactory


def _make_openai_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="m-1",
        provider="openai",
        model_name="gpt-4o",
        display_name="GPT-4o",
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=None,
        is_active=True,
        is_default=False,
        created_at=now,
        updated_at=now,
    )


class TestStreamUsage:
    def test_openai_chat_model_has_stream_usage_true(self) -> None:
        factory = LLMFactory()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            chat = factory.create(_make_openai_model(), temperature=0.0)
        # stream_usage 속성이 True인지 확인 (ChatOpenAI는 pydantic 모델)
        assert getattr(chat, "stream_usage", False) is True
