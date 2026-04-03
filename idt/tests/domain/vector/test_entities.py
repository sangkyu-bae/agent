"""Tests for vector domain entities.

TDD: These tests are written first before implementation.
Domain tests use NO mocks as per CLAUDE.md rules.
"""
import pytest
from datetime import datetime
from typing import List

from src.domain.vector.value_objects import DocumentId, DocumentType
from src.domain.vector.entities import Document


class TestDocument:
    """Tests for Document entity."""

    def test_create_document_without_id(self) -> None:
        """Documents can be created without an id (before persistence)."""
        doc = Document(
            id=None,
            content="Test document content",
            vector=[0.1, 0.2, 0.3],
            metadata={"type": "policy"},
        )
        assert doc.id is None
        assert doc.content == "Test document content"
        assert doc.vector == [0.1, 0.2, 0.3]
        assert doc.metadata == {"type": "policy"}

    def test_create_document_with_id(self) -> None:
        doc_id = DocumentId("doc-123")
        doc = Document(
            id=doc_id,
            content="Test content",
            vector=[0.1, 0.2],
            metadata={},
        )
        assert doc.id == doc_id
        assert doc.id.value == "doc-123"

    def test_document_with_score(self) -> None:
        """Documents returned from search can have a similarity score."""
        doc = Document(
            id=DocumentId("doc-123"),
            content="Test content",
            vector=[0.1, 0.2],
            metadata={},
            score=0.95,
        )
        assert doc.score == 0.95

    def test_document_without_score(self) -> None:
        doc = Document(
            id=DocumentId("doc-123"),
            content="Test content",
            vector=[0.1, 0.2],
            metadata={},
        )
        assert doc.score is None

    def test_empty_content_raises_error(self) -> None:
        with pytest.raises(ValueError, match="Document content cannot be empty"):
            Document(
                id=None,
                content="",
                vector=[0.1, 0.2],
                metadata={},
            )

    def test_whitespace_only_content_raises_error(self) -> None:
        with pytest.raises(ValueError, match="Document content cannot be empty"):
            Document(
                id=None,
                content="   ",
                vector=[0.1, 0.2],
                metadata={},
            )

    def test_empty_vector_raises_error(self) -> None:
        with pytest.raises(ValueError, match="Document vector cannot be empty"):
            Document(
                id=None,
                content="Test content",
                vector=[],
                metadata={},
            )

    def test_invalid_score_too_high_raises_error(self) -> None:
        with pytest.raises(ValueError, match="Score must be between 0 and 1"):
            Document(
                id=None,
                content="Test content",
                vector=[0.1],
                metadata={},
                score=1.5,
            )

    def test_invalid_score_negative_raises_error(self) -> None:
        with pytest.raises(ValueError, match="Score must be between 0 and 1"):
            Document(
                id=None,
                content="Test content",
                vector=[0.1],
                metadata={},
                score=-0.1,
            )

    def test_score_boundary_zero(self) -> None:
        doc = Document(
            id=None,
            content="Test content",
            vector=[0.1],
            metadata={},
            score=0.0,
        )
        assert doc.score == 0.0

    def test_score_boundary_one(self) -> None:
        doc = Document(
            id=None,
            content="Test content",
            vector=[0.1],
            metadata={},
            score=1.0,
        )
        assert doc.score == 1.0

    def test_document_equality(self) -> None:
        doc1 = Document(
            id=DocumentId("doc-123"),
            content="Test content",
            vector=[0.1, 0.2],
            metadata={"key": "value"},
        )
        doc2 = Document(
            id=DocumentId("doc-123"),
            content="Test content",
            vector=[0.1, 0.2],
            metadata={"key": "value"},
        )
        assert doc1 == doc2

    def test_document_is_immutable(self) -> None:
        doc = Document(
            id=DocumentId("doc-123"),
            content="Test content",
            vector=[0.1, 0.2],
            metadata={},
        )
        with pytest.raises(AttributeError):
            doc.content = "New content"

    def test_document_vector_dimension(self) -> None:
        vector = [0.1] * 1536  # OpenAI ada-002 dimension
        doc = Document(
            id=None,
            content="Test content",
            vector=vector,
            metadata={},
        )
        assert doc.vector_dimension == 1536

    def test_document_with_document_type_metadata(self) -> None:
        doc = Document(
            id=None,
            content="Test content",
            vector=[0.1],
            metadata={"document_type": "policy", "category": "finance"},
        )
        assert doc.metadata["document_type"] == "policy"

    def test_document_with_parent_child_metadata(self) -> None:
        """Documents can have parent/child relationship metadata for RAG."""
        doc = Document(
            id=DocumentId("child-1"),
            content="Child chunk content",
            vector=[0.1, 0.2],
            metadata={
                "parent_id": "parent-doc-1",
                "chunk_index": "0",
                "is_child": "true",
            },
        )
        assert doc.metadata["parent_id"] == "parent-doc-1"
        assert doc.metadata["is_child"] == "true"

    def test_document_has_score_true(self) -> None:
        doc = Document(
            id=None,
            content="Test content",
            vector=[0.1],
            metadata={},
            score=0.8,
        )
        assert doc.has_score() is True

    def test_document_has_score_false(self) -> None:
        doc = Document(
            id=None,
            content="Test content",
            vector=[0.1],
            metadata={},
        )
        assert doc.has_score() is False
