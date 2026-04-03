"""Tests for OpenAIProvider implementation."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List

from pydantic import BaseModel

from src.domain.compressor.value_objects.llm_config import LLMConfig
from src.domain.compressor.interfaces.llm_provider_interface import LLMProviderInterface
from src.infrastructure.compressor.providers.openai_provider import OpenAIProvider


class SampleSchema(BaseModel):
    """Sample schema for testing structured output."""

    is_relevant: bool
    reason: str


class TestOpenAIProviderCreation:
    """Tests for OpenAIProvider creation."""

    def test_create_provider_with_config(self):
        """OpenAIProvider should be created with LLMConfig."""
        config = LLMConfig(
            provider="openai",
            model_name="gpt-4o-mini",
            api_key="test-key",
        )

        provider = OpenAIProvider(config)

        assert provider is not None
        assert isinstance(provider, LLMProviderInterface)

    def test_provider_stores_model_name(self):
        """Provider should store model name from config."""
        config = LLMConfig(
            provider="openai",
            model_name="gpt-4o-mini",
            api_key="test-key",
        )

        provider = OpenAIProvider(config)

        assert provider.get_model_name() == "gpt-4o-mini"

    def test_provider_name_is_openai(self):
        """Provider name should be 'openai'."""
        config = LLMConfig(
            provider="openai",
            model_name="gpt-4o-mini",
            api_key="test-key",
        )

        provider = OpenAIProvider(config)

        assert provider.get_provider_name() == "openai"


class TestOpenAIProviderGenerate:
    """Tests for OpenAIProvider.generate method."""

    @pytest.fixture
    def config(self) -> LLMConfig:
        return LLMConfig(
            provider="openai",
            model_name="gpt-4o-mini",
            temperature=0.0,
            max_tokens=1000,
            api_key="test-key",
        )

    @pytest.fixture
    def mock_response(self) -> MagicMock:
        """Create mock OpenAI response."""
        mock = MagicMock()
        mock.choices = [MagicMock()]
        mock.choices[0].message.content = "Test response content"
        return mock

    async def test_generate_returns_string(
        self, config: LLMConfig, mock_response: MagicMock
    ):
        """generate should return string response from OpenAI."""
        with patch(
            "src.infrastructure.compressor.providers.openai_provider.AsyncOpenAI"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            provider = OpenAIProvider(config)
            result = await provider.generate("Test prompt")

            assert isinstance(result, str)
            assert result == "Test response content"

    async def test_generate_calls_openai_with_correct_params(
        self, config: LLMConfig, mock_response: MagicMock
    ):
        """generate should call OpenAI API with correct parameters."""
        with patch(
            "src.infrastructure.compressor.providers.openai_provider.AsyncOpenAI"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            provider = OpenAIProvider(config)
            await provider.generate("Test prompt")

            mock_client.chat.completions.create.assert_called_once()
            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            assert call_kwargs["model"] == "gpt-4o-mini"
            assert call_kwargs["temperature"] == 0.0
            assert call_kwargs["max_tokens"] == 1000


class TestOpenAIProviderGenerateBatch:
    """Tests for OpenAIProvider.generate_batch method."""

    @pytest.fixture
    def config(self) -> LLMConfig:
        return LLMConfig(
            provider="openai",
            model_name="gpt-4o-mini",
            api_key="test-key",
        )

    def _create_mock_response(self, content: str) -> MagicMock:
        """Create mock OpenAI response with given content."""
        mock = MagicMock()
        mock.choices = [MagicMock()]
        mock.choices[0].message.content = content
        return mock

    async def test_generate_batch_returns_list_of_strings(self, config: LLMConfig):
        """generate_batch should return list of string responses."""
        with patch(
            "src.infrastructure.compressor.providers.openai_provider.AsyncOpenAI"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=[
                    self._create_mock_response("Response 1"),
                    self._create_mock_response("Response 2"),
                    self._create_mock_response("Response 3"),
                ]
            )
            mock_client_class.return_value = mock_client

            provider = OpenAIProvider(config)
            prompts = ["Prompt 1", "Prompt 2", "Prompt 3"]
            results = await provider.generate_batch(prompts)

            assert isinstance(results, list)
            assert len(results) == 3
            assert results == ["Response 1", "Response 2", "Response 3"]

    async def test_generate_batch_uses_asyncio_gather(self, config: LLMConfig):
        """generate_batch should use asyncio.gather for parallel execution."""
        with patch(
            "src.infrastructure.compressor.providers.openai_provider.AsyncOpenAI"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=[
                    self._create_mock_response(f"Response {i}") for i in range(5)
                ]
            )
            mock_client_class.return_value = mock_client

            provider = OpenAIProvider(config)
            prompts = [f"Prompt {i}" for i in range(5)]
            results = await provider.generate_batch(prompts)

            assert len(results) == 5
            assert mock_client.chat.completions.create.call_count == 5

    async def test_generate_batch_empty_list_returns_empty(self, config: LLMConfig):
        """generate_batch with empty list should return empty list."""
        with patch(
            "src.infrastructure.compressor.providers.openai_provider.AsyncOpenAI"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            provider = OpenAIProvider(config)
            results = await provider.generate_batch([])

            assert results == []


class TestOpenAIProviderGenerateStructured:
    """Tests for OpenAIProvider.generate_structured method."""

    @pytest.fixture
    def config(self) -> LLMConfig:
        return LLMConfig(
            provider="openai",
            model_name="gpt-4o-mini",
            api_key="test-key",
        )

    def _create_json_response(self, content: str) -> MagicMock:
        """Create mock OpenAI response with JSON content."""
        mock = MagicMock()
        mock.choices = [MagicMock()]
        mock.choices[0].message.content = content
        return mock

    async def test_generate_structured_returns_pydantic_model(
        self, config: LLMConfig
    ):
        """generate_structured should return Pydantic model instance."""
        json_content = '{"is_relevant": true, "reason": "Test reason"}'

        with patch(
            "src.infrastructure.compressor.providers.openai_provider.AsyncOpenAI"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=self._create_json_response(json_content)
            )
            mock_client_class.return_value = mock_client

            provider = OpenAIProvider(config)
            result = await provider.generate_structured("Test prompt", SampleSchema)

            assert isinstance(result, SampleSchema)
            assert result.is_relevant is True
            assert result.reason == "Test reason"

    async def test_generate_structured_uses_json_mode(self, config: LLMConfig):
        """generate_structured should use JSON response format."""
        json_content = '{"is_relevant": false, "reason": "Not relevant"}'

        with patch(
            "src.infrastructure.compressor.providers.openai_provider.AsyncOpenAI"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=self._create_json_response(json_content)
            )
            mock_client_class.return_value = mock_client

            provider = OpenAIProvider(config)
            await provider.generate_structured("Test prompt", SampleSchema)

            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            assert call_kwargs["response_format"] == {"type": "json_object"}


class TestOpenAIProviderApiKey:
    """Tests for API key handling."""

    def test_api_key_passed_to_client(self):
        """API key from config should be passed to AsyncOpenAI client."""
        config = LLMConfig(
            provider="openai",
            model_name="gpt-4o-mini",
            api_key="my-secret-key",
        )

        with patch(
            "src.infrastructure.compressor.providers.openai_provider.AsyncOpenAI"
        ) as mock_client_class:
            OpenAIProvider(config)

            mock_client_class.assert_called_once_with(api_key="my-secret-key")

    def test_none_api_key_passed_to_client(self):
        """None API key should be passed (relies on env variable)."""
        config = LLMConfig(
            provider="openai",
            model_name="gpt-4o-mini",
            api_key=None,
        )

        with patch(
            "src.infrastructure.compressor.providers.openai_provider.AsyncOpenAI"
        ) as mock_client_class:
            OpenAIProvider(config)

            mock_client_class.assert_called_once_with(api_key=None)
