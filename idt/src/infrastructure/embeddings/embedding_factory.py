"""Embedding Factory for creating embedding instances.

Provides factory methods to create embedding implementations
based on provider configuration.
"""
from enum import Enum
from typing import Optional

from langchain_openai import OpenAIEmbeddings

from src.domain.vector.interfaces import EmbeddingInterface


_FALLBACK_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class EmbeddingProvider(Enum):
    """Supported embedding providers."""

    OPENAI = "openai"

    @classmethod
    def from_string(cls, provider_str: str) -> "EmbeddingProvider":
        """Create EmbeddingProvider from string (case-insensitive).

        Args:
            provider_str: String representation of the provider

        Returns:
            EmbeddingProvider enum value

        Raises:
            ValueError: If provider_str is not a valid provider
        """
        provider_lower = provider_str.lower()
        for member in cls:
            if member.value == provider_lower:
                return member
        raise ValueError(f"Unknown embedding provider: {provider_str}")


class _OpenAIEmbeddingAdapter(EmbeddingInterface):
    """OpenAI embedding adapter implementing EmbeddingInterface."""

    def __init__(self, model_name: str = "text-embedding-3-small") -> None:
        self._model_name = model_name
        self._embeddings = OpenAIEmbeddings(model=model_name)

    async def embed_text(self, text: str) -> list[float]:
        return await self._embeddings.aembed_query(text)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embeddings.aembed_documents(texts)

    def get_dimension(self) -> int:
        if self._model_name not in _FALLBACK_DIMENSIONS:
            raise ValueError(f"Unknown model dimension for: {self._model_name}")
        return _FALLBACK_DIMENSIONS[self._model_name]


class EmbeddingFactory:
    """Factory for creating embedding instances."""

    @staticmethod
    def create(
        provider: EmbeddingProvider,
        model_name: Optional[str] = None,
    ) -> EmbeddingInterface:
        """Create an embedding instance for the given provider.

        Args:
            provider: The embedding provider to use
            model_name: Optional model name (provider-specific defaults apply)

        Returns:
            An EmbeddingInterface implementation

        Raises:
            ValueError: If the provider is not supported
        """
        if provider == EmbeddingProvider.OPENAI:
            model = model_name or "text-embedding-3-small"
            return _OpenAIEmbeddingAdapter(model_name=model)

        raise ValueError(f"Unsupported provider: {provider}")

    @staticmethod
    def create_from_string(
        provider: str,
        model_name: Optional[str] = None,
    ) -> EmbeddingInterface:
        """Create an embedding instance using string provider name.

        Args:
            provider: The provider name as string (e.g., "openai")
            model_name: Optional model name

        Returns:
            An EmbeddingInterface implementation
        """
        provider_enum = EmbeddingProvider.from_string(provider)
        return EmbeddingFactory.create(provider_enum, model_name)
