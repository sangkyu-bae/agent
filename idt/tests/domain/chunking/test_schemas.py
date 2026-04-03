"""Tests for domain chunking schemas."""
import pytest
from pydantic import ValidationError

from src.domain.chunking.schemas import (
    ChunkRequest,
    ChunkResponse,
    ChunkResult,
)


class TestChunkRequest:
    """Tests for ChunkRequest DTO."""

    def test_valid_request(self):
        """Valid request should be created successfully."""
        request = ChunkRequest(
            document_id="doc_123",
            content="Test content",
            strategy_type="full_token"
        )

        assert request.document_id == "doc_123"
        assert request.content == "Test content"
        assert request.strategy_type == "full_token"

    def test_document_id_required(self):
        """document_id is required."""
        with pytest.raises(ValidationError):
            ChunkRequest(
                content="Test content",
                strategy_type="full_token"
            )

    def test_content_required(self):
        """content is required."""
        with pytest.raises(ValidationError):
            ChunkRequest(
                document_id="doc_123",
                strategy_type="full_token"
            )

    def test_strategy_type_required(self):
        """strategy_type is required."""
        with pytest.raises(ValidationError):
            ChunkRequest(
                document_id="doc_123",
                content="Test content"
            )

    def test_strategy_type_validation(self):
        """strategy_type must be a valid type."""
        with pytest.raises(ValidationError):
            ChunkRequest(
                document_id="doc_123",
                content="Test content",
                strategy_type="invalid_type"
            )

    def test_valid_strategy_types(self):
        """All valid strategy types should be accepted."""
        for strategy in ["full_token", "parent_child", "semantic"]:
            request = ChunkRequest(
                document_id="doc_123",
                content="Test content",
                strategy_type=strategy
            )
            assert request.strategy_type == strategy

    def test_optional_metadata(self):
        """metadata should be optional."""
        request = ChunkRequest(
            document_id="doc_123",
            content="Test content",
            strategy_type="full_token"
        )

        assert request.metadata is None

    def test_metadata_with_values(self):
        """metadata should accept dictionary values."""
        request = ChunkRequest(
            document_id="doc_123",
            content="Test content",
            strategy_type="full_token",
            metadata={"user_id": "user_456", "source": "test"}
        )

        assert request.metadata == {"user_id": "user_456", "source": "test"}

    def test_optional_chunk_config(self):
        """chunk_size and chunk_overlap should be optional."""
        request = ChunkRequest(
            document_id="doc_123",
            content="Test content",
            strategy_type="full_token"
        )

        assert request.chunk_size is None
        assert request.chunk_overlap is None

    def test_custom_chunk_config(self):
        """Custom chunk_size and chunk_overlap should be accepted."""
        request = ChunkRequest(
            document_id="doc_123",
            content="Test content",
            strategy_type="full_token",
            chunk_size=1000,
            chunk_overlap=100
        )

        assert request.chunk_size == 1000
        assert request.chunk_overlap == 100


class TestChunkResult:
    """Tests for ChunkResult DTO."""

    def test_valid_result(self):
        """Valid result should be created successfully."""
        result = ChunkResult(
            chunk_id="chunk_1",
            content="Chunk content",
            chunk_type="full",
            chunk_index=0,
            total_chunks=5,
            metadata={"document_id": "doc_123"}
        )

        assert result.chunk_id == "chunk_1"
        assert result.content == "Chunk content"
        assert result.chunk_type == "full"
        assert result.chunk_index == 0
        assert result.total_chunks == 5

    def test_parent_result_with_children(self):
        """Parent result should include children_ids."""
        result = ChunkResult(
            chunk_id="parent_1",
            content="Parent content",
            chunk_type="parent",
            chunk_index=0,
            total_chunks=1,
            children_ids=["child_1", "child_2"],
            metadata={}
        )

        assert result.children_ids == ["child_1", "child_2"]

    def test_child_result_with_parent(self):
        """Child result should include parent_id."""
        result = ChunkResult(
            chunk_id="child_1",
            content="Child content",
            chunk_type="child",
            chunk_index=0,
            total_chunks=3,
            parent_id="parent_1",
            metadata={}
        )

        assert result.parent_id == "parent_1"


class TestChunkResponse:
    """Tests for ChunkResponse DTO."""

    def test_valid_response(self):
        """Valid response should be created successfully."""
        chunks = [
            ChunkResult(
                chunk_id="chunk_1",
                content="Content 1",
                chunk_type="full",
                chunk_index=0,
                total_chunks=2,
                metadata={}
            ),
            ChunkResult(
                chunk_id="chunk_2",
                content="Content 2",
                chunk_type="full",
                chunk_index=1,
                total_chunks=2,
                metadata={}
            )
        ]

        response = ChunkResponse(
            document_id="doc_123",
            strategy_type="full_token",
            chunks=chunks,
            total_chunks=2
        )

        assert response.document_id == "doc_123"
        assert response.strategy_type == "full_token"
        assert len(response.chunks) == 2
        assert response.total_chunks == 2

    def test_empty_chunks(self):
        """Response with empty chunks should be valid."""
        response = ChunkResponse(
            document_id="doc_123",
            strategy_type="full_token",
            chunks=[],
            total_chunks=0
        )

        assert response.chunks == []
        assert response.total_chunks == 0

    def test_response_fields_required(self):
        """All main fields should be required."""
        with pytest.raises(ValidationError):
            ChunkResponse(
                document_id="doc_123",
                strategy_type="full_token"
                # Missing chunks and total_chunks
            )

    def test_response_serialization(self):
        """Response should serialize to dict correctly."""
        chunks = [
            ChunkResult(
                chunk_id="chunk_1",
                content="Content",
                chunk_type="full",
                chunk_index=0,
                total_chunks=1,
                metadata={"key": "value"}
            )
        ]

        response = ChunkResponse(
            document_id="doc_123",
            strategy_type="full_token",
            chunks=chunks,
            total_chunks=1
        )

        data = response.model_dump()

        assert data["document_id"] == "doc_123"
        assert data["strategy_type"] == "full_token"
        assert len(data["chunks"]) == 1
        assert data["chunks"][0]["chunk_id"] == "chunk_1"
