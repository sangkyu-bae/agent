"""Tests for domain chunking interfaces."""
import pytest
from abc import ABC
from typing import List
from langchain_core.documents import Document

from src.domain.chunking.interfaces import ChunkingStrategy


class TestChunkingStrategyInterface:
    """Tests for ChunkingStrategy abstract interface."""

    def test_is_abstract_class(self):
        """ChunkingStrategy should be an abstract class."""
        assert issubclass(ChunkingStrategy, ABC)

    def test_cannot_instantiate_directly(self):
        """ChunkingStrategy cannot be instantiated directly."""
        with pytest.raises(TypeError):
            ChunkingStrategy()

    def test_has_chunk_method(self):
        """ChunkingStrategy must define chunk method."""
        assert hasattr(ChunkingStrategy, "chunk")
        assert callable(getattr(ChunkingStrategy, "chunk"))

    def test_has_get_strategy_name_method(self):
        """ChunkingStrategy must define get_strategy_name method."""
        assert hasattr(ChunkingStrategy, "get_strategy_name")
        assert callable(getattr(ChunkingStrategy, "get_strategy_name"))

    def test_has_get_chunk_size_method(self):
        """ChunkingStrategy must define get_chunk_size method."""
        assert hasattr(ChunkingStrategy, "get_chunk_size")
        assert callable(getattr(ChunkingStrategy, "get_chunk_size"))

    def test_concrete_implementation_works(self):
        """Concrete implementation should work correctly."""

        class ConcreteStrategy(ChunkingStrategy):
            def chunk(self, documents: List[Document]) -> List[Document]:
                return documents

            def get_strategy_name(self) -> str:
                return "test_strategy"

            def get_chunk_size(self) -> int:
                return 1000

        strategy = ConcreteStrategy()

        assert strategy.get_strategy_name() == "test_strategy"
        assert strategy.get_chunk_size() == 1000

        docs = [Document(page_content="test")]
        assert strategy.chunk(docs) == docs

    def test_must_implement_all_methods(self):
        """Concrete class must implement all abstract methods."""

        class IncompleteStrategy(ChunkingStrategy):
            def chunk(self, documents: List[Document]) -> List[Document]:
                return documents

            # Missing get_strategy_name and get_chunk_size

        with pytest.raises(TypeError):
            IncompleteStrategy()
