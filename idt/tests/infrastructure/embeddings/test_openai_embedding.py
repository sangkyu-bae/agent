"""Tests for OpenAI embedding implementation.

Infrastructure tests use mocks as per CLAUDE.md rules.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List

from src.infrastructure.embeddings.openai_embedding import OpenAIEmbedding


class TestOpenAIEmbedding:
    """Tests for OpenAIEmbedding implementation."""

    @pytest.fixture
    def mock_openai_embeddings(self) -> MagicMock:
        """Create a mock LangChain OpenAIEmbeddings."""
        mock = MagicMock()
        return mock

    def test_implements_embedding_interface(self) -> None:
        """OpenAIEmbedding should implement EmbeddingInterface."""
        from src.domain.vector.interfaces import EmbeddingInterface

        with patch(
            "src.infrastructure.embeddings.openai_embedding.OpenAIEmbeddings"
        ):
            embedding = OpenAIEmbedding(model_name="text-embedding-3-small")
            assert isinstance(embedding, EmbeddingInterface)

    def test_default_model_name(self) -> None:
        """Default model should be text-embedding-3-small."""
        with patch(
            "src.infrastructure.embeddings.openai_embedding.OpenAIEmbeddings"
        ) as mock_cls:
            OpenAIEmbedding()
            mock_cls.assert_called_once_with(model="text-embedding-3-small")

    def test_custom_model_name(self) -> None:
        """Should accept custom model name."""
        with patch(
            "src.infrastructure.embeddings.openai_embedding.OpenAIEmbeddings"
        ) as mock_cls:
            OpenAIEmbedding(model_name="text-embedding-ada-002")
            mock_cls.assert_called_once_with(model="text-embedding-ada-002")

    @pytest.mark.asyncio
    async def test_embed_text_returns_vector(self) -> None:
        """embed_text should return a list of floats."""
        expected_vector = [0.1, 0.2, 0.3] * 512  # 1536 dimensions

        with patch(
            "src.infrastructure.embeddings.openai_embedding.OpenAIEmbeddings"
        ) as mock_cls:
            mock_instance = MagicMock()
            mock_instance.aembed_query = AsyncMock(return_value=expected_vector)
            mock_cls.return_value = mock_instance

            embedding = OpenAIEmbedding()
            result = await embedding.embed_text("test text")

            assert result == expected_vector
            mock_instance.aembed_query.assert_called_once_with("test text")

    @pytest.mark.asyncio
    async def test_embed_documents_returns_vectors(self) -> None:
        """embed_documents should return a list of vectors."""
        expected_vectors = [
            [0.1, 0.2, 0.3] * 512,
            [0.4, 0.5, 0.6] * 512,
        ]

        with patch(
            "src.infrastructure.embeddings.openai_embedding.OpenAIEmbeddings"
        ) as mock_cls:
            mock_instance = MagicMock()
            mock_instance.aembed_documents = AsyncMock(return_value=expected_vectors)
            mock_cls.return_value = mock_instance

            embedding = OpenAIEmbedding()
            result = await embedding.embed_documents(["text 1", "text 2"])

            assert result == expected_vectors
            mock_instance.aembed_documents.assert_called_once_with(["text 1", "text 2"])

    @pytest.mark.asyncio
    async def test_embed_documents_empty_list(self) -> None:
        """embed_documents with empty list should return empty list."""
        with patch(
            "src.infrastructure.embeddings.openai_embedding.OpenAIEmbeddings"
        ) as mock_cls:
            mock_instance = MagicMock()
            mock_instance.aembed_documents = AsyncMock(return_value=[])
            mock_cls.return_value = mock_instance

            embedding = OpenAIEmbedding()
            result = await embedding.embed_documents([])

            assert result == []

    def test_get_dimension_text_embedding_3_small(self) -> None:
        """text-embedding-3-small should return 1536 dimensions."""
        with patch(
            "src.infrastructure.embeddings.openai_embedding.OpenAIEmbeddings"
        ):
            embedding = OpenAIEmbedding(model_name="text-embedding-3-small")
            assert embedding.get_dimension() == 1536

    def test_get_dimension_text_embedding_3_large(self) -> None:
        """text-embedding-3-large should return 3072 dimensions."""
        with patch(
            "src.infrastructure.embeddings.openai_embedding.OpenAIEmbeddings"
        ):
            embedding = OpenAIEmbedding(model_name="text-embedding-3-large")
            assert embedding.get_dimension() == 3072

    def test_get_dimension_text_embedding_ada_002(self) -> None:
        """text-embedding-ada-002 should return 1536 dimensions."""
        with patch(
            "src.infrastructure.embeddings.openai_embedding.OpenAIEmbeddings"
        ):
            embedding = OpenAIEmbedding(model_name="text-embedding-ada-002")
            assert embedding.get_dimension() == 1536

    def test_get_dimension_unknown_model_raises_error(self) -> None:
        """Unknown model should raise ValueError."""
        with patch(
            "src.infrastructure.embeddings.openai_embedding.OpenAIEmbeddings"
        ):
            embedding = OpenAIEmbedding(model_name="unknown-model")
            with pytest.raises(ValueError, match="Unknown model dimension"):
                embedding.get_dimension()
