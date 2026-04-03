"""Tests for ChunkingStrategyConfig mapping."""
import pytest

from src.domain.pipeline.enums.document_category import DocumentCategory
from src.domain.pipeline.config.chunking_strategy_config import (
    CATEGORY_CHUNKING_CONFIG,
    get_chunking_config,
)
from src.domain.chunking.value_objects import ChunkingConfig


class TestCategoryChunkingConfigMapping:
    """Test CATEGORY_CHUNKING_CONFIG mapping."""

    def test_it_system_has_2000_chunk_size(self):
        """Test IT_SYSTEM uses 2000 token chunks."""
        config = CATEGORY_CHUNKING_CONFIG[DocumentCategory.IT_SYSTEM]
        assert config.chunk_size == 2000
        assert config.chunk_overlap == 200

    def test_hr_has_400_chunk_size(self):
        """Test HR uses 400 token chunks with 100 overlap."""
        config = CATEGORY_CHUNKING_CONFIG[DocumentCategory.HR]
        assert config.chunk_size == 400
        assert config.chunk_overlap == 100

    def test_loan_finance_has_800_chunk_size(self):
        """Test LOAN_FINANCE uses 800 token chunks."""
        config = CATEGORY_CHUNKING_CONFIG[DocumentCategory.LOAN_FINANCE]
        assert config.chunk_size == 800
        assert config.chunk_overlap == 100

    def test_security_access_has_600_chunk_size(self):
        """Test SECURITY_ACCESS uses 600 token chunks."""
        config = CATEGORY_CHUNKING_CONFIG[DocumentCategory.SECURITY_ACCESS]
        assert config.chunk_size == 600
        assert config.chunk_overlap == 100

    def test_accounting_legal_has_1000_chunk_size(self):
        """Test ACCOUNTING_LEGAL uses 1000 token chunks with 150 overlap."""
        config = CATEGORY_CHUNKING_CONFIG[DocumentCategory.ACCOUNTING_LEGAL]
        assert config.chunk_size == 1000
        assert config.chunk_overlap == 150

    def test_general_has_1000_chunk_size(self):
        """Test GENERAL uses 1000 token chunks with 100 overlap."""
        config = CATEGORY_CHUNKING_CONFIG[DocumentCategory.GENERAL]
        assert config.chunk_size == 1000
        assert config.chunk_overlap == 100

    def test_all_categories_have_config(self):
        """Test all categories have chunking config."""
        for category in DocumentCategory:
            assert category in CATEGORY_CHUNKING_CONFIG
            config = CATEGORY_CHUNKING_CONFIG[category]
            assert isinstance(config, ChunkingConfig)


class TestGetChunkingConfig:
    """Test get_chunking_config function."""

    def test_returns_config_for_valid_category(self):
        """Test returns ChunkingConfig for valid category."""
        config = get_chunking_config(DocumentCategory.IT_SYSTEM)
        assert isinstance(config, ChunkingConfig)
        assert config.chunk_size == 2000

    def test_returns_correct_config_for_hr(self):
        """Test returns correct config for HR."""
        config = get_chunking_config(DocumentCategory.HR)
        assert config.chunk_size == 400
        assert config.chunk_overlap == 100

    def test_general_as_fallback(self):
        """Test GENERAL category works as fallback."""
        config = get_chunking_config(DocumentCategory.GENERAL)
        assert config.chunk_size == 1000
        assert config.chunk_overlap == 100

    def test_all_configs_have_valid_encoding_model(self):
        """Test all configs have valid encoding model."""
        for category in DocumentCategory:
            config = get_chunking_config(category)
            assert config.encoding_model == "cl100k_base"
