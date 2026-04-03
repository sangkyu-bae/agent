"""Tests for RetrieverInterface abstract base class.

Tests:
- ABC verification
- Method signature verification
- Concrete implementation requirement
"""
import pytest
from abc import ABC
from typing import List, Optional, Tuple
from unittest.mock import AsyncMock

from src.domain.retriever.interfaces.retriever_interface import RetrieverInterface
from src.domain.retriever.value_objects.metadata_filter import MetadataFilter
from src.domain.vector.entities import Document


class TestRetrieverInterfaceIsABC:
    """Tests for RetrieverInterface ABC status."""

    def test_retriever_interface_is_abc(self):
        """RetrieverInterface should be an abstract base class."""
        assert issubclass(RetrieverInterface, ABC)

    def test_cannot_instantiate_directly(self):
        """Cannot instantiate RetrieverInterface directly."""
        with pytest.raises(TypeError) as exc_info:
            RetrieverInterface()
        assert "abstract" in str(exc_info.value).lower()


class TestRetrieverInterfaceMethodSignatures:
    """Tests for method signatures."""

    def test_retrieve_is_abstract(self):
        """retrieve() should be an abstract method."""
        assert hasattr(RetrieverInterface, "retrieve")
        assert getattr(RetrieverInterface.retrieve, "__isabstractmethod__", False)

    def test_retrieve_with_scores_is_abstract(self):
        """retrieve_with_scores() should be an abstract method."""
        assert hasattr(RetrieverInterface, "retrieve_with_scores")
        assert getattr(
            RetrieverInterface.retrieve_with_scores, "__isabstractmethod__", False
        )

    def test_retrieve_by_metadata_is_abstract(self):
        """retrieve_by_metadata() should be an abstract method."""
        assert hasattr(RetrieverInterface, "retrieve_by_metadata")
        assert getattr(
            RetrieverInterface.retrieve_by_metadata, "__isabstractmethod__", False
        )

    def test_get_retriever_name_is_abstract(self):
        """get_retriever_name() should be an abstract method."""
        assert hasattr(RetrieverInterface, "get_retriever_name")
        assert getattr(
            RetrieverInterface.get_retriever_name, "__isabstractmethod__", False
        )


class ConcreteRetriever(RetrieverInterface):
    """Concrete implementation for testing."""

    def __init__(self, name: str = "test-retriever"):
        self._name = name
        self._documents: List[Document] = []

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[MetadataFilter] = None,
    ) -> List[Document]:
        return self._documents[:top_k]

    async def retrieve_with_scores(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[MetadataFilter] = None,
    ) -> List[Tuple[Document, float]]:
        return [(doc, 0.9) for doc in self._documents[:top_k]]

    async def retrieve_by_metadata(
        self,
        filters: MetadataFilter,
        top_k: int = 10,
    ) -> List[Document]:
        return self._documents[:top_k]

    def get_retriever_name(self) -> str:
        return self._name


class TestConcreteImplementation:
    """Tests for concrete implementation requirements."""

    def test_can_instantiate_concrete_implementation(self):
        """Should be able to instantiate concrete implementation."""
        retriever = ConcreteRetriever()
        assert retriever is not None

    def test_concrete_is_subclass(self):
        """Concrete implementation should be subclass of RetrieverInterface."""
        assert issubclass(ConcreteRetriever, RetrieverInterface)

    def test_concrete_is_instance(self):
        """Concrete implementation instance should be instance of RetrieverInterface."""
        retriever = ConcreteRetriever()
        assert isinstance(retriever, RetrieverInterface)


class TestConcreteRetrieverMethods:
    """Tests for concrete retriever method behavior."""

    @pytest.fixture
    def retriever(self):
        return ConcreteRetriever(name="test-retriever")

    @pytest.mark.asyncio
    async def test_retrieve_returns_documents(self, retriever):
        """retrieve() should return list of Documents."""
        result = await retriever.retrieve("test query")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_retrieve_accepts_top_k(self, retriever):
        """retrieve() should accept top_k parameter."""
        result = await retriever.retrieve("test query", top_k=5)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_retrieve_accepts_filters(self, retriever):
        """retrieve() should accept filters parameter."""
        filters = MetadataFilter(user_id="user-123")
        result = await retriever.retrieve("test query", filters=filters)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_retrieve_with_scores_returns_tuples(self, retriever):
        """retrieve_with_scores() should return list of (Document, float) tuples."""
        result = await retriever.retrieve_with_scores("test query")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_retrieve_by_metadata_returns_documents(self, retriever):
        """retrieve_by_metadata() should return list of Documents."""
        filters = MetadataFilter(document_id="doc-123")
        result = await retriever.retrieve_by_metadata(filters)
        assert isinstance(result, list)

    def test_get_retriever_name_returns_string(self, retriever):
        """get_retriever_name() should return string."""
        name = retriever.get_retriever_name()
        assert isinstance(name, str)
        assert name == "test-retriever"


class TestPartialImplementation:
    """Tests that partial implementation fails."""

    def test_missing_retrieve_raises_error(self):
        """Class missing retrieve() should raise TypeError."""

        class PartialRetriever(RetrieverInterface):
            async def retrieve_with_scores(
                self, query, top_k=10, filters=None
            ):
                return []

            async def retrieve_by_metadata(self, filters, top_k=10):
                return []

            def get_retriever_name(self):
                return "partial"

        with pytest.raises(TypeError):
            PartialRetriever()

    def test_missing_retrieve_with_scores_raises_error(self):
        """Class missing retrieve_with_scores() should raise TypeError."""

        class PartialRetriever(RetrieverInterface):
            async def retrieve(self, query, top_k=10, filters=None):
                return []

            async def retrieve_by_metadata(self, filters, top_k=10):
                return []

            def get_retriever_name(self):
                return "partial"

        with pytest.raises(TypeError):
            PartialRetriever()

    def test_missing_retrieve_by_metadata_raises_error(self):
        """Class missing retrieve_by_metadata() should raise TypeError."""

        class PartialRetriever(RetrieverInterface):
            async def retrieve(self, query, top_k=10, filters=None):
                return []

            async def retrieve_with_scores(
                self, query, top_k=10, filters=None
            ):
                return []

            def get_retriever_name(self):
                return "partial"

        with pytest.raises(TypeError):
            PartialRetriever()

    def test_missing_get_retriever_name_raises_error(self):
        """Class missing get_retriever_name() should raise TypeError."""

        class PartialRetriever(RetrieverInterface):
            async def retrieve(self, query, top_k=10, filters=None):
                return []

            async def retrieve_with_scores(
                self, query, top_k=10, filters=None
            ):
                return []

            async def retrieve_by_metadata(self, filters, top_k=10):
                return []

        with pytest.raises(TypeError):
            PartialRetriever()
