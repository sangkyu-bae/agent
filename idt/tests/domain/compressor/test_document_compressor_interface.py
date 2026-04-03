"""Tests for DocumentCompressorInterface."""
import pytest
from abc import ABC
from typing import List

from langchain_core.documents import Document

from src.domain.compressor.interfaces.document_compressor_interface import (
    DocumentCompressorInterface,
)
from src.domain.compressor.entities.compressed_document import CompressedDocument
from src.domain.compressor.value_objects.relevance_result import RelevanceResult


class MockDocumentCompressor(DocumentCompressorInterface):
    """Mock implementation for testing the interface."""

    def __init__(self, compressor_name: str = "mock"):
        self._compressor_name = compressor_name

    async def compress(
        self, documents: List[Document], query: str
    ) -> List[Document]:
        return [doc for doc in documents if "relevant" in doc.page_content.lower()]

    async def compress_with_scores(
        self, documents: List[Document], query: str
    ) -> List[CompressedDocument]:
        results = []
        for doc in documents:
            is_relevant = "relevant" in doc.page_content.lower()
            score = 0.9 if is_relevant else 0.1
            relevance = RelevanceResult(is_relevant=is_relevant, score=score)
            results.append(CompressedDocument(document=doc, relevance=relevance))
        return results

    def get_compressor_name(self) -> str:
        return self._compressor_name


class TestDocumentCompressorInterfaceContract:
    """Tests for DocumentCompressorInterface contract."""

    def test_interface_is_abstract_base_class(self):
        """DocumentCompressorInterface should be an abstract base class."""
        assert issubclass(DocumentCompressorInterface, ABC)

    def test_cannot_instantiate_interface_directly(self):
        """Should not be able to instantiate the interface directly."""
        with pytest.raises(TypeError):
            DocumentCompressorInterface()

    def test_interface_has_compress_method(self):
        """Interface should define compress method."""
        assert hasattr(DocumentCompressorInterface, "compress")

    def test_interface_has_compress_with_scores_method(self):
        """Interface should define compress_with_scores method."""
        assert hasattr(DocumentCompressorInterface, "compress_with_scores")

    def test_interface_has_get_compressor_name_method(self):
        """Interface should define get_compressor_name method."""
        assert hasattr(DocumentCompressorInterface, "get_compressor_name")


class TestMockDocumentCompressorImplementation:
    """Tests for mock implementation to verify interface works correctly."""

    @pytest.fixture
    def compressor(self) -> MockDocumentCompressor:
        return MockDocumentCompressor()

    @pytest.fixture
    def sample_documents(self) -> List[Document]:
        return [
            Document(page_content="This is a relevant document", metadata={"id": "1"}),
            Document(page_content="This is not related", metadata={"id": "2"}),
            Document(page_content="Another relevant document", metadata={"id": "3"}),
        ]

    async def test_compress_returns_list_of_documents(
        self, compressor: MockDocumentCompressor, sample_documents: List[Document]
    ):
        """compress should return a list of Document objects."""
        results = await compressor.compress(sample_documents, "test query")

        assert isinstance(results, list)
        assert all(isinstance(doc, Document) for doc in results)

    async def test_compress_filters_documents(
        self, compressor: MockDocumentCompressor, sample_documents: List[Document]
    ):
        """compress should filter documents based on relevance."""
        results = await compressor.compress(sample_documents, "test query")

        assert len(results) == 2
        assert all("relevant" in doc.page_content.lower() for doc in results)

    async def test_compress_with_scores_returns_compressed_documents(
        self, compressor: MockDocumentCompressor, sample_documents: List[Document]
    ):
        """compress_with_scores should return CompressedDocument objects."""
        results = await compressor.compress_with_scores(sample_documents, "test query")

        assert isinstance(results, list)
        assert all(isinstance(doc, CompressedDocument) for doc in results)

    async def test_compress_with_scores_includes_all_documents(
        self, compressor: MockDocumentCompressor, sample_documents: List[Document]
    ):
        """compress_with_scores should return all documents with scores."""
        results = await compressor.compress_with_scores(sample_documents, "test query")

        assert len(results) == len(sample_documents)

    async def test_compress_with_scores_contains_relevance_info(
        self, compressor: MockDocumentCompressor, sample_documents: List[Document]
    ):
        """compress_with_scores results should have relevance information."""
        results = await compressor.compress_with_scores(sample_documents, "test query")

        for result in results:
            assert isinstance(result.is_relevant, bool)
            assert 0.0 <= result.score <= 1.0

    def test_get_compressor_name_returns_string(
        self, compressor: MockDocumentCompressor
    ):
        """get_compressor_name should return the compressor name."""
        assert compressor.get_compressor_name() == "mock"

    def test_mock_compressor_is_instance_of_interface(
        self, compressor: MockDocumentCompressor
    ):
        """Mock compressor should be instance of DocumentCompressorInterface."""
        assert isinstance(compressor, DocumentCompressorInterface)

    async def test_compress_empty_list_returns_empty(
        self, compressor: MockDocumentCompressor
    ):
        """compress with empty list should return empty list."""
        results = await compressor.compress([], "test query")
        assert results == []

    async def test_compress_with_scores_empty_list_returns_empty(
        self, compressor: MockDocumentCompressor
    ):
        """compress_with_scores with empty list should return empty list."""
        results = await compressor.compress_with_scores([], "test query")
        assert results == []
