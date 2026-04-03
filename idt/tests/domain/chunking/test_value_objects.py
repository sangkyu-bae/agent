"""Tests for domain chunking value objects."""
import pytest
from dataclasses import FrozenInstanceError

from src.domain.chunking.value_objects import ChunkingConfig, ChunkMetadata


class TestChunkingConfig:
    """Tests for ChunkingConfig value object."""

    def test_create_valid_config(self):
        """Valid config should be created successfully."""
        config = ChunkingConfig(chunk_size=1000, chunk_overlap=100)

        assert config.chunk_size == 1000
        assert config.chunk_overlap == 100

    def test_chunk_size_must_be_positive(self):
        """chunk_size must be a positive integer."""
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            ChunkingConfig(chunk_size=0, chunk_overlap=100)

        with pytest.raises(ValueError, match="chunk_size must be positive"):
            ChunkingConfig(chunk_size=-100, chunk_overlap=100)

    def test_chunk_overlap_must_be_less_than_chunk_size(self):
        """chunk_overlap must be less than chunk_size."""
        with pytest.raises(ValueError, match="chunk_overlap must be less than chunk_size"):
            ChunkingConfig(chunk_size=100, chunk_overlap=100)

        with pytest.raises(ValueError, match="chunk_overlap must be less than chunk_size"):
            ChunkingConfig(chunk_size=100, chunk_overlap=150)

    def test_chunk_overlap_can_be_zero(self):
        """chunk_overlap of 0 is valid."""
        config = ChunkingConfig(chunk_size=1000, chunk_overlap=0)

        assert config.chunk_overlap == 0

    def test_encoding_model_default_value(self):
        """encoding_model should default to cl100k_base."""
        config = ChunkingConfig(chunk_size=1000, chunk_overlap=100)

        assert config.encoding_model == "cl100k_base"

    def test_encoding_model_custom_value(self):
        """encoding_model can be customized."""
        config = ChunkingConfig(
            chunk_size=1000,
            chunk_overlap=100,
            encoding_model="p50k_base"
        )

        assert config.encoding_model == "p50k_base"

    def test_frozen_dataclass_immutable(self):
        """ChunkingConfig should be immutable (frozen)."""
        config = ChunkingConfig(chunk_size=1000, chunk_overlap=100)

        with pytest.raises(FrozenInstanceError):
            config.chunk_size = 2000


class TestChunkMetadata:
    """Tests for ChunkMetadata value object."""

    def test_create_parent_metadata(self):
        """Parent chunk metadata should be created successfully."""
        metadata = ChunkMetadata(
            chunk_type="parent",
            chunk_index=0,
            total_chunks=1,
            parent_id=None,
            children_ids=["child_1", "child_2"]
        )

        assert metadata.chunk_type == "parent"
        assert metadata.children_ids == ["child_1", "child_2"]

    def test_create_child_metadata(self):
        """Child chunk metadata should be created successfully."""
        metadata = ChunkMetadata(
            chunk_type="child",
            chunk_index=0,
            total_chunks=3,
            parent_id="parent_1"
        )

        assert metadata.chunk_type == "child"
        assert metadata.parent_id == "parent_1"

    def test_create_full_metadata(self):
        """Full chunk metadata should be created successfully."""
        metadata = ChunkMetadata(
            chunk_type="full",
            chunk_index=2,
            total_chunks=5
        )

        assert metadata.chunk_type == "full"
        assert metadata.chunk_index == 2
        assert metadata.total_chunks == 5

    def test_invalid_chunk_type_raises_error(self):
        """Invalid chunk_type should raise ValueError."""
        with pytest.raises(ValueError, match="chunk_type must be one of"):
            ChunkMetadata(
                chunk_type="invalid",
                chunk_index=0,
                total_chunks=1
            )

    def test_child_requires_parent_id(self):
        """Child chunk must have parent_id."""
        with pytest.raises(ValueError, match="parent_id is required for child chunks"):
            ChunkMetadata(
                chunk_type="child",
                chunk_index=0,
                total_chunks=1,
                parent_id=None
            )

    def test_is_parent_method(self):
        """is_parent() should return True for parent chunks."""
        parent = ChunkMetadata(
            chunk_type="parent",
            chunk_index=0,
            total_chunks=1
        )
        child = ChunkMetadata(
            chunk_type="child",
            chunk_index=0,
            total_chunks=1,
            parent_id="parent_1"
        )

        assert parent.is_parent() is True
        assert child.is_parent() is False

    def test_is_child_method(self):
        """is_child() should return True for child chunks."""
        parent = ChunkMetadata(
            chunk_type="parent",
            chunk_index=0,
            total_chunks=1
        )
        child = ChunkMetadata(
            chunk_type="child",
            chunk_index=0,
            total_chunks=1,
            parent_id="parent_1"
        )

        assert parent.is_child() is False
        assert child.is_child() is True

    def test_to_dict_method(self):
        """to_dict() should return dictionary representation."""
        metadata = ChunkMetadata(
            chunk_type="parent",
            chunk_index=0,
            total_chunks=3,
            parent_id=None,
            children_ids=["c1", "c2"]
        )

        result = metadata.to_dict()

        assert result == {
            "chunk_type": "parent",
            "chunk_index": 0,
            "total_chunks": 3,
            "parent_id": None,
            "children_ids": ["c1", "c2"]
        }

    def test_to_dict_excludes_none_children_ids(self):
        """to_dict() should handle None children_ids."""
        metadata = ChunkMetadata(
            chunk_type="full",
            chunk_index=1,
            total_chunks=5
        )

        result = metadata.to_dict()

        assert result == {
            "chunk_type": "full",
            "chunk_index": 1,
            "total_chunks": 5,
            "parent_id": None,
            "children_ids": None
        }

    def test_semantic_chunk_type_valid(self):
        """semantic is a valid chunk_type."""
        metadata = ChunkMetadata(
            chunk_type="semantic",
            chunk_index=0,
            total_chunks=1
        )

        assert metadata.chunk_type == "semantic"
