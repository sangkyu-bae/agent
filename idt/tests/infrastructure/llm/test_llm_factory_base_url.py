"""LLMFactory: LLM-MODEL-REG-002 self-host base_url 전달/더미키 검증."""
import os
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from src.domain.llm_model.entity import LlmModel
from src.infrastructure.llm.llm_factory import LLMFactory


def _make_model(
    provider: str = "openai",
    model_name: str = "Qwen2.5-32B-Instruct",
    api_key_env: str = "QWEN_API_KEY",
    base_url: str | None = None,
) -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="m-qwen",
        provider=provider,
        model_name=model_name,
        display_name="사내 Qwen",
        description=None,
        api_key_env=api_key_env,
        max_tokens=None,
        is_active=True,
        is_default=False,
        created_at=now,
        updated_at=now,
        base_url=base_url,
    )


class TestOpenAIBaseUrl:
    @patch.dict(os.environ, {"QWEN_API_KEY": "sk-internal"})
    def test_base_url_passed_to_chat_openai(self) -> None:
        factory = LLMFactory()
        model = _make_model(base_url="http://10.0.0.5:8000/v1")

        chat = factory.create(model)

        assert isinstance(chat, ChatOpenAI)
        assert chat.openai_api_base == "http://10.0.0.5:8000/v1"

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    def test_no_base_url_keeps_default_endpoint(self) -> None:
        factory = LLMFactory()
        model = _make_model(
            model_name="gpt-4o",
            api_key_env="OPENAI_API_KEY",
            base_url=None,
        )

        chat = factory.create(model)

        # base_url 미지정 → 커스텀 엔드포인트 아님 (기존 동작)
        assert chat.openai_api_base != "http://10.0.0.5:8000/v1"

    @patch.dict(os.environ, {}, clear=True)
    def test_base_url_allows_empty_api_key(self) -> None:
        """vLLM 인증 미사용: base_url 있으면 키 없어도 EMPTY로 통과."""
        factory = LLMFactory()
        model = _make_model(base_url="http://10.0.0.5:8000/v1")

        chat = factory.create(model)  # RuntimeError 발생하지 않아야 함

        assert isinstance(chat, ChatOpenAI)
        assert chat.openai_api_base == "http://10.0.0.5:8000/v1"

    @patch.dict(os.environ, {}, clear=True)
    def test_no_base_url_still_requires_api_key(self) -> None:
        """base_url 없으면 기존대로 키 필수 (회귀 방지)."""
        factory = LLMFactory()
        model = _make_model(
            model_name="gpt-4o", api_key_env="OPENAI_API_KEY", base_url=None
        )

        with pytest.raises(RuntimeError, match="환경변수"):
            factory.create(model)


class TestOllamaBaseUrl:
    def test_base_url_passed_to_chat_ollama(self) -> None:
        factory = LLMFactory()
        model = _make_model(
            provider="ollama",
            model_name="qwen2.5",
            api_key_env="",
            base_url="http://10.0.0.9:11434",
        )

        chat = factory.create(model)

        assert isinstance(chat, ChatOllama)
        assert chat.base_url == "http://10.0.0.9:11434"
