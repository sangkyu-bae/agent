"""Tests for CompressedDocument entity."""
import pytest

from langchain_core.documents import Document

from src.domain.compressor.entities.compressed_document import CompressedDocument
from src.domain.compressor.value_objects.relevance_result import RelevanceResult


class TestCompressedDocumentCreation:
    """Tests for CompressedDocument creation."""

    def test_create_compressed_document_with_all_fields(self):
        """CompressedDocument should be created with document and relevance result."""
        document = Document(page_content="Test content", metadata={"id": "doc1"})
        relevance = RelevanceResult(is_relevant=True, score=0.85, reasoning="Relevant")

        compressed = CompressedDocument(document=document, relevance=relevance)

        assert compressed.document == document
        assert compressed.relevance == relevance

    def test_compressed_document_stores_original_document(self):
        """CompressedDocument should preserve original document."""
        document = Document(
            page_content="Original content",
            metadata={"source": "test.pdf", "page": 1},
        )
        relevance = RelevanceResult(is_relevant=True, score=0.9)

        compressed = CompressedDocument(document=document, relevance=relevance)

        assert compressed.document.page_content == "Original content"
        assert compressed.document.metadata["source"] == "test.pdf"
        assert compressed.document.metadata["page"] == 1


class TestCompressedDocumentProperties:
    """Tests for CompressedDocument convenience properties."""

    def test_is_relevant_property_returns_relevance_result(self):
        """is_relevant property should delegate to relevance result."""
        document = Document(page_content="Test")
        relevance = RelevanceResult(is_relevant=True, score=0.8)

        compressed = CompressedDocument(document=document, relevance=relevance)

        assert compressed.is_relevant is True

    def test_is_relevant_false_when_not_relevant(self):
        """is_relevant should return False when document is not relevant."""
        document = Document(page_content="Test")
        relevance = RelevanceResult(is_relevant=False, score=0.2)

        compressed = CompressedDocument(document=document, relevance=relevance)

        assert compressed.is_relevant is False

    def test_score_property_returns_relevance_score(self):
        """score property should return the relevance score."""
        document = Document(page_content="Test")
        relevance = RelevanceResult(is_relevant=True, score=0.75)

        compressed = CompressedDocument(document=document, relevance=relevance)

        assert compressed.score == 0.75

    def test_reasoning_property_returns_relevance_reasoning(self):
        """reasoning property should return the relevance reasoning."""
        document = Document(page_content="Test")
        relevance = RelevanceResult(
            is_relevant=True, score=0.9, reasoning="Matches query"
        )

        compressed = CompressedDocument(document=document, relevance=relevance)

        assert compressed.reasoning == "Matches query"

    def test_reasoning_property_returns_none_when_no_reasoning(self):
        """reasoning property should return None when no reasoning."""
        document = Document(page_content="Test")
        relevance = RelevanceResult(is_relevant=True, score=0.9)

        compressed = CompressedDocument(document=document, relevance=relevance)

        assert compressed.reasoning is None

    def test_page_content_property_returns_document_content(self):
        """page_content property should return document content."""
        document = Document(page_content="Test content here")
        relevance = RelevanceResult(is_relevant=True, score=0.8)

        compressed = CompressedDocument(document=document, relevance=relevance)

        assert compressed.page_content == "Test content here"

    def test_metadata_property_returns_document_metadata(self):
        """metadata property should return document metadata."""
        document = Document(page_content="Test", metadata={"key": "value"})
        relevance = RelevanceResult(is_relevant=True, score=0.8)

        compressed = CompressedDocument(document=document, relevance=relevance)

        assert compressed.metadata == {"key": "value"}


class TestCompressedDocumentImmutability:
    """Tests for CompressedDocument immutability."""

    def test_compressed_document_is_immutable(self):
        """CompressedDocument should be immutable (frozen dataclass)."""
        document = Document(page_content="Test")
        relevance = RelevanceResult(is_relevant=True, score=0.8)
        compressed = CompressedDocument(document=document, relevance=relevance)

        with pytest.raises(AttributeError):
            compressed.relevance = RelevanceResult(is_relevant=False, score=0.1)


class TestCompressedDocumentEquality:
    """Tests for CompressedDocument equality."""

    def test_equal_documents_are_equal(self):
        """Two CompressedDocuments with same values should be equal."""
        document = Document(page_content="Test", metadata={"id": "1"})
        relevance = RelevanceResult(is_relevant=True, score=0.8)

        compressed1 = CompressedDocument(document=document, relevance=relevance)
        compressed2 = CompressedDocument(document=document, relevance=relevance)

        assert compressed1 == compressed2

    def test_different_relevance_are_not_equal(self):
        """CompressedDocuments with different relevance should not be equal."""
        document = Document(page_content="Test")
        relevance1 = RelevanceResult(is_relevant=True, score=0.8)
        relevance2 = RelevanceResult(is_relevant=False, score=0.2)

        compressed1 = CompressedDocument(document=document, relevance=relevance1)
        compressed2 = CompressedDocument(document=document, relevance=relevance2)

        assert compressed1 != compressed2
