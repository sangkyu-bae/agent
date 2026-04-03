"""Tests for Embedding Factory.

Infrastructure tests use mocks as per CLAUDE.md rules.
"""
import pytest
from unittest.mock import patch

from src.infrastructure.embeddings.embedding_factory import (
    EmbeddingFactory,
    EmbeddingProvider,
)
from src.domain.vector.interfaces import EmbeddingInterface


class TestEmbeddingProvider:
    """Tests for EmbeddingProvider enum."""

    def test_openai_provider(self) -> None:
        assert EmbeddingProvider.OPENAI.value == "openai"

    def test_from_string_openai(self) -> None:
        provider = EmbeddingProvider.from_string("openai")
        assert provider == EmbeddingProvider.OPENAI

    def test_from_string_case_insensitive(self) -> None:
        provider = EmbeddingProvider.from_string("OPENAI")
        assert provider == EmbeddingProvider.OPENAI

    def test_from_string_invalid_raises_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            EmbeddingProvider.from_string("unknown")


class TestEmbeddingFactory:
    """Tests for EmbeddingFactory."""

    def test_create_openai_embedding(self) -> None:
        """Should create OpenAI embedding with default model."""
        with patch(
            "src.infrastructure.embeddings.embedding_factory.OpenAIEmbeddings"
        ):
            embedding = EmbeddingFactory.create(provider=EmbeddingProvider.OPENAI)
            assert isinstance(embedding, EmbeddingInterface)

    def test_create_openai_embedding_with_custom_model(self) -> None:
        """Should create OpenAI embedding with custom model."""
        with patch(
            "src.infrastructure.embeddings.embedding_factory.OpenAIEmbeddings"
        ) as mock_cls:
            EmbeddingFactory.create(
                provider=EmbeddingProvider.OPENAI,
                model_name="text-embedding-3-large",
            )
            mock_cls.assert_called_once_with(model="text-embedding-3-large")

    def test_create_from_string_provider(self) -> None:
        """Should accept string provider name."""
        with patch(
            "src.infrastructure.embeddings.embedding_factory.OpenAIEmbeddings"
        ):
            embedding = EmbeddingFactory.create_from_string(provider="openai")
            assert isinstance(embedding, EmbeddingInterface)

    def test_create_from_string_with_model(self) -> None:
        """Should accept string provider with model name."""
        with patch(
            "src.infrastructure.embeddings.embedding_factory.OpenAIEmbeddings"
        ) as mock_cls:
            EmbeddingFactory.create_from_string(
                provider="openai",
                model_name="text-embedding-ada-002",
            )
            mock_cls.assert_called_once_with(model="text-embedding-ada-002")

    def test_create_from_string_invalid_provider(self) -> None:
        """Should raise error for invalid provider string."""
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            EmbeddingFactory.create_from_string(provider="invalid")
