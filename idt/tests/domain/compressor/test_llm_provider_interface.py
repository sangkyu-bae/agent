"""Tests for LLMProviderInterface."""
import pytest
from abc import ABC
from typing import List, Type

from pydantic import BaseModel

from src.domain.compressor.interfaces.llm_provider_interface import LLMProviderInterface


class SampleSchema(BaseModel):
    """Sample schema for testing structured output."""

    name: str
    value: int


class MockLLMProvider(LLMProviderInterface):
    """Mock implementation for testing the interface."""

    def __init__(self, provider_name: str = "mock", model_name: str = "mock-model"):
        self._provider_name = provider_name
        self._model_name = model_name

    async def generate(self, prompt: str) -> str:
        return f"Response to: {prompt}"

    async def generate_batch(self, prompts: List[str]) -> List[str]:
        return [f"Response to: {p}" for p in prompts]

    async def generate_structured(
        self, prompt: str, schema: Type[BaseModel]
    ) -> BaseModel:
        return SampleSchema(name="test", value=42)

    def get_provider_name(self) -> str:
        return self._provider_name

    def get_model_name(self) -> str:
        return self._model_name


class TestLLMProviderInterfaceContract:
    """Tests for LLMProviderInterface contract."""

    def test_interface_is_abstract_base_class(self):
        """LLMProviderInterface should be an abstract base class."""
        assert issubclass(LLMProviderInterface, ABC)

    def test_cannot_instantiate_interface_directly(self):
        """Should not be able to instantiate the interface directly."""
        with pytest.raises(TypeError):
            LLMProviderInterface()

    def test_interface_has_generate_method(self):
        """Interface should define generate method."""
        assert hasattr(LLMProviderInterface, "generate")

    def test_interface_has_generate_batch_method(self):
        """Interface should define generate_batch method."""
        assert hasattr(LLMProviderInterface, "generate_batch")

    def test_interface_has_generate_structured_method(self):
        """Interface should define generate_structured method."""
        assert hasattr(LLMProviderInterface, "generate_structured")

    def test_interface_has_get_provider_name_method(self):
        """Interface should define get_provider_name method."""
        assert hasattr(LLMProviderInterface, "get_provider_name")

    def test_interface_has_get_model_name_method(self):
        """Interface should define get_model_name method."""
        assert hasattr(LLMProviderInterface, "get_model_name")


class TestMockLLMProviderImplementation:
    """Tests for mock implementation to verify interface works correctly."""

    @pytest.fixture
    def provider(self) -> MockLLMProvider:
        return MockLLMProvider()

    async def test_generate_returns_string(self, provider: MockLLMProvider):
        """generate should return a string response."""
        result = await provider.generate("test prompt")

        assert isinstance(result, str)
        assert "test prompt" in result

    async def test_generate_batch_returns_list_of_strings(
        self, provider: MockLLMProvider
    ):
        """generate_batch should return list of string responses."""
        prompts = ["prompt1", "prompt2", "prompt3"]
        results = await provider.generate_batch(prompts)

        assert isinstance(results, list)
        assert len(results) == len(prompts)
        assert all(isinstance(r, str) for r in results)

    async def test_generate_structured_returns_pydantic_model(
        self, provider: MockLLMProvider
    ):
        """generate_structured should return a pydantic model instance."""
        result = await provider.generate_structured("test", SampleSchema)

        assert isinstance(result, BaseModel)
        assert isinstance(result, SampleSchema)

    def test_get_provider_name_returns_string(self, provider: MockLLMProvider):
        """get_provider_name should return provider name."""
        assert provider.get_provider_name() == "mock"

    def test_get_model_name_returns_string(self, provider: MockLLMProvider):
        """get_model_name should return model name."""
        assert provider.get_model_name() == "mock-model"

    def test_mock_provider_is_instance_of_interface(self, provider: MockLLMProvider):
        """Mock provider should be instance of LLMProviderInterface."""
        assert isinstance(provider, LLMProviderInterface)
