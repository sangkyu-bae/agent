"""Tests for ChunkingStrategyFactory."""
import pytest
from enum import Enum

from src.infrastructure.chunking.chunking_factory import (
    ChunkingStrategyFactory,
    StrategyType,
)
from src.infrastructure.chunking.strategies.full_token_strategy import (
    FullTokenStrategy,
)
from src.infrastructure.chunking.strategies.parent_child_strategy import (
    ParentChildStrategy,
)
from src.infrastructure.chunking.strategies.semantic_strategy import SemanticStrategy
from src.domain.chunking.interfaces import ChunkingStrategy


class TestStrategyType:
    """Tests for StrategyType enum."""

    def test_is_enum(self):
        """StrategyType should be an Enum."""
        assert issubclass(StrategyType, Enum)

    def test_has_full_token_type(self):
        """StrategyType should have FULL_TOKEN."""
        assert hasattr(StrategyType, "FULL_TOKEN")
        assert StrategyType.FULL_TOKEN.value == "full_token"

    def test_has_parent_child_type(self):
        """StrategyType should have PARENT_CHILD."""
        assert hasattr(StrategyType, "PARENT_CHILD")
        assert StrategyType.PARENT_CHILD.value == "parent_child"


class TestChunkingStrategyFactory:
    """Tests for ChunkingStrategyFactory."""

    def test_create_full_token_strategy(self):
        """Factory should create FullTokenStrategy."""
        strategy = ChunkingStrategyFactory.create_strategy(StrategyType.FULL_TOKEN)

        assert isinstance(strategy, FullTokenStrategy)
        assert isinstance(strategy, ChunkingStrategy)
        assert strategy.get_strategy_name() == "full_token"

    def test_create_full_token_strategy_by_string(self):
        """Factory should create FullTokenStrategy from string."""
        strategy = ChunkingStrategyFactory.create_strategy("full_token")

        assert isinstance(strategy, FullTokenStrategy)

    def test_create_parent_child_strategy(self):
        """Factory should create ParentChildStrategy."""
        strategy = ChunkingStrategyFactory.create_strategy(
            StrategyType.PARENT_CHILD
        )

        assert isinstance(strategy, ParentChildStrategy)
        assert isinstance(strategy, ChunkingStrategy)
        assert strategy.get_strategy_name() == "parent_child"

    def test_create_parent_child_strategy_by_string(self):
        """Factory should create ParentChildStrategy from string."""
        strategy = ChunkingStrategyFactory.create_strategy("parent_child")

        assert isinstance(strategy, ParentChildStrategy)

    def test_invalid_strategy_type_raises_error(self):
        """Invalid strategy type should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown strategy type"):
            ChunkingStrategyFactory.create_strategy("invalid_type")

    def test_full_token_default_chunk_size(self):
        """FullTokenStrategy should have 2000 token default chunk size."""
        strategy = ChunkingStrategyFactory.create_strategy(StrategyType.FULL_TOKEN)

        assert strategy.get_chunk_size() == 2000

    def test_parent_child_default_chunk_size(self):
        """ParentChildStrategy should have 500 token default (child) chunk size."""
        strategy = ChunkingStrategyFactory.create_strategy(
            StrategyType.PARENT_CHILD
        )

        assert strategy.get_chunk_size() == 500

    def test_full_token_custom_config(self):
        """Factory should accept custom config for FullTokenStrategy."""
        strategy = ChunkingStrategyFactory.create_strategy(
            StrategyType.FULL_TOKEN,
            chunk_size=1000,
            chunk_overlap=100
        )

        assert strategy.get_chunk_size() == 1000

    def test_parent_child_custom_config(self):
        """Factory should accept custom config for ParentChildStrategy."""
        strategy = ChunkingStrategyFactory.create_strategy(
            StrategyType.PARENT_CHILD,
            parent_chunk_size=1000,
            child_chunk_size=200,
            child_chunk_overlap=20
        )

        assert strategy.get_chunk_size() == 200

    def test_list_available_strategies(self):
        """Factory should list available strategy types."""
        strategies = ChunkingStrategyFactory.list_strategies()

        assert "full_token" in strategies
        assert "parent_child" in strategies

    def test_create_semantic_strategy(self):
        """Factory should create SemanticStrategy."""
        strategy = ChunkingStrategyFactory.create_strategy(StrategyType.SEMANTIC)

        assert isinstance(strategy, SemanticStrategy)
        assert isinstance(strategy, ChunkingStrategy)
        assert strategy.get_strategy_name() == "semantic"

    def test_create_semantic_strategy_by_string(self):
        """Factory should create SemanticStrategy from string."""
        strategy = ChunkingStrategyFactory.create_strategy("semantic")

        assert isinstance(strategy, SemanticStrategy)

    def test_semantic_default_chunk_size(self):
        """SemanticStrategy should have 1000 token default max chunk size."""
        strategy = ChunkingStrategyFactory.create_strategy(StrategyType.SEMANTIC)

        assert strategy.get_chunk_size() == 1000

    def test_semantic_custom_config(self):
        """Factory should accept custom config for SemanticStrategy."""
        strategy = ChunkingStrategyFactory.create_strategy(
            StrategyType.SEMANTIC,
            chunk_size=500,
            min_chunk_size=100,
        )

        assert strategy.get_chunk_size() == 500

    def test_list_available_strategies_includes_semantic(self):
        """Factory strategy list should include semantic."""
        strategies = ChunkingStrategyFactory.list_strategies()

        assert "semantic" in strategies

    def test_strategy_type_has_semantic(self):
        """StrategyType enum should have SEMANTIC."""
        assert hasattr(StrategyType, "SEMANTIC")
        assert StrategyType.SEMANTIC.value == "semantic"
