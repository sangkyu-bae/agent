"""LLMFactory 단위 테스트 — provider별 LLM 인스턴스 생성 검증."""
from datetime import datetime
from unittest.mock import patch

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel
from src.infrastructure.llm.llm_factory import LLMFactory


def _make_model(
    provider: str = "openai",
    model_name: str = "gpt-4o",
    api_key_env: str = "OPENAI_API_KEY",
) -> LlmModel:
    return LlmModel(
        id="test-id",
        provider=provider,
        model_name=model_name,
        display_name="Test Model",
        description=None,
        api_key_env=api_key_env,
        max_tokens=128000,
        is_active=True,
        is_default=True,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


class TestLLMFactory:
    def test_implements_interface(self) -> None:
        factory = LLMFactory()
        assert isinstance(factory, LLMFactoryInterface)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"})
    def test_create_openai_returns_chat_openai(self) -> None:
        factory = LLMFactory()
        model = _make_model(provider="openai", model_name="gpt-4o")

        llm = factory.create(model, temperature=0.5)

        assert isinstance(llm, ChatOpenAI)

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"})
    def test_create_anthropic_returns_chat_anthropic(self) -> None:
        factory = LLMFactory()
        model = _make_model(
            provider="anthropic",
            model_name="claude-sonnet-4-6",
            api_key_env="ANTHROPIC_API_KEY",
        )

        llm = factory.create(model, temperature=0.3)

        assert isinstance(llm, ChatAnthropic)

    def test_create_ollama_returns_chat_ollama(self) -> None:
        factory = LLMFactory()
        model = _make_model(
            provider="ollama",
            model_name="llama3.2",
            api_key_env="",
        )

        llm = factory.create(model, temperature=0.7)

        assert isinstance(llm, ChatOllama)

    def test_unsupported_provider_raises_value_error(self) -> None:
        factory = LLMFactory()
        model = _make_model(provider="unknown_provider")

        with pytest.raises(ValueError, match="지원하지 않는 provider"):
            factory.create(model)

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_api_key_raises_runtime_error(self) -> None:
        factory = LLMFactory()
        model = _make_model(provider="openai", api_key_env="OPENAI_API_KEY")

        with pytest.raises(RuntimeError, match="환경변수"):
            factory.create(model)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"})
    def test_default_temperature_is_zero(self) -> None:
        factory = LLMFactory()
        model = _make_model(provider="openai")

        llm = factory.create(model)

        assert isinstance(llm, ChatOpenAI)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"})
    def test_temperature_passed_correctly(self) -> None:
        factory = LLMFactory()
        model = _make_model(provider="openai")

        llm = factory.create(model, temperature=1.5)

        assert llm.temperature == 1.5

    @patch.dict("os.environ", {}, clear=True)
    def test_ollama_no_api_key_required(self) -> None:
        factory = LLMFactory()
        model = _make_model(
            provider="ollama",
            model_name="llama3.2",
            api_key_env="",
        )

        llm = factory.create(model, temperature=0.5)

        assert isinstance(llm, ChatOllama)
