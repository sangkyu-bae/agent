"""OpenAI embedding implementation.

Wraps LangChain's OpenAIEmbeddings to implement domain EmbeddingInterface.
"""
from typing import List

from langchain_openai import OpenAIEmbeddings

from src.domain.vector.interfaces import EmbeddingInterface
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)

_FALLBACK_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class OpenAIEmbedding(EmbeddingInterface):
    """OpenAI embedding implementation using LangChain."""

    def __init__(self, model_name: str = "text-embedding-3-small") -> None:
        self._model_name = model_name
        self._embeddings = OpenAIEmbeddings(model=model_name)

    async def embed_text(self, text: str) -> List[float]:
        """Generate an embedding vector for a single text."""
        try:
            return await self._embeddings.aembed_query(text)
        except Exception as e:
            logger.error("Embedding text failed", exception=e, model=self._model_name)
            raise

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate embedding vectors for multiple texts."""
        try:
            return await self._embeddings.aembed_documents(texts)
        except Exception as e:
            logger.error(
                "Embedding documents failed",
                exception=e,
                model=self._model_name,
                count=len(texts),
            )
            raise

    def get_dimension(self) -> int:
        if self._model_name not in _FALLBACK_DIMENSIONS:
            raise ValueError(f"Unknown model dimension for: {self._model_name}")
        return _FALLBACK_DIMENSIONS[self._model_name]
