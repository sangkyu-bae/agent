"""Factory for creating chunking strategies."""
import re
from enum import Enum
from typing import List, Union

from src.domain.chunking.interfaces import ChunkingStrategy
from src.domain.chunking.value_objects import ChunkingConfig
from src.infrastructure.chunking.strategies.full_token_strategy import (
    FullTokenStrategy,
)
from src.infrastructure.chunking.strategies.parent_child_strategy import (
    ParentChildStrategy,
)
from src.infrastructure.chunking.strategies.semantic_strategy import SemanticStrategy
from src.infrastructure.chunking.strategies.section_aware_strategy import (
    SectionAwareChunkingStrategy,
)
from src.infrastructure.chunking.strategies.clause_aware_strategy import (
    ClauseAwareStrategy,
)


class StrategyType(Enum):
    """Enumeration of available chunking strategy types."""

    FULL_TOKEN = "full_token"
    PARENT_CHILD = "parent_child"
    SEMANTIC = "semantic"
    SECTION_AWARE = "section_aware"
    CLAUSE_AWARE = "clause_aware"


class ChunkingStrategyFactory:
    """Factory for creating chunking strategy instances."""

    # Default configurations
    DEFAULT_FULL_TOKEN_SIZE = 2000
    DEFAULT_FULL_TOKEN_OVERLAP = 200
    DEFAULT_PARENT_SIZE = 2000
    DEFAULT_CHILD_SIZE = 500
    DEFAULT_CHILD_OVERLAP = 50
    DEFAULT_SEMANTIC_MAX_SIZE = 1000
    DEFAULT_SEMANTIC_MIN_SIZE = 200

    @classmethod
    def create_strategy(
        cls,
        strategy_type: Union[StrategyType, str],
        **kwargs
    ) -> ChunkingStrategy:
        """Create a chunking strategy instance.

        Args:
            strategy_type: Type of strategy to create (enum or string).
            **kwargs: Optional configuration overrides.
                For FULL_TOKEN: chunk_size, chunk_overlap
                For PARENT_CHILD: parent_chunk_size, child_chunk_size,
                                  child_chunk_overlap

        Returns:
            ChunkingStrategy instance.

        Raises:
            ValueError: If strategy_type is unknown.
        """
        # Convert string to enum if needed
        if isinstance(strategy_type, str):
            strategy_type = cls._resolve_strategy_type(strategy_type)

        if strategy_type == StrategyType.FULL_TOKEN:
            return cls._create_full_token_strategy(**kwargs)
        elif strategy_type == StrategyType.PARENT_CHILD:
            return cls._create_parent_child_strategy(**kwargs)
        elif strategy_type == StrategyType.SEMANTIC:
            return cls._create_semantic_strategy(**kwargs)
        elif strategy_type == StrategyType.SECTION_AWARE:
            return cls._create_section_aware_strategy(**kwargs)
        elif strategy_type == StrategyType.CLAUSE_AWARE:
            return cls._create_clause_aware_strategy(**kwargs)
        else:
            raise ValueError(f"Unknown strategy type: {strategy_type}")

    @classmethod
    def _resolve_strategy_type(cls, type_str: str) -> StrategyType:
        """Resolve string to StrategyType enum.

        Args:
            type_str: Strategy type string.

        Returns:
            StrategyType enum value.

        Raises:
            ValueError: If type_str doesn't match any strategy.
        """
        type_str = type_str.lower()
        for strategy in StrategyType:
            if strategy.value == type_str:
                return strategy
        raise ValueError(f"Unknown strategy type: {type_str}")

    @classmethod
    def _create_full_token_strategy(cls, **kwargs) -> FullTokenStrategy:
        """Create FullTokenStrategy with configuration.

        Args:
            **kwargs: chunk_size, chunk_overlap overrides.

        Returns:
            FullTokenStrategy instance.
        """
        chunk_size = kwargs.get("chunk_size", cls.DEFAULT_FULL_TOKEN_SIZE)
        chunk_overlap = kwargs.get("chunk_overlap", cls.DEFAULT_FULL_TOKEN_OVERLAP)

        config = ChunkingConfig(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        return FullTokenStrategy(config)

    @classmethod
    def _create_parent_child_strategy(cls, **kwargs) -> ParentChildStrategy:
        """Create ParentChildStrategy with configuration.

        Args:
            **kwargs: parent_chunk_size, child_chunk_size,
                      child_chunk_overlap, table_flattening overrides.

        Returns:
            ParentChildStrategy instance.
        """
        parent_chunk_size = kwargs.get(
            "parent_chunk_size", cls.DEFAULT_PARENT_SIZE
        )
        child_chunk_size = kwargs.get(
            "child_chunk_size", cls.DEFAULT_CHILD_SIZE
        )
        child_chunk_overlap = kwargs.get(
            "child_chunk_overlap", cls.DEFAULT_CHILD_OVERLAP
        )
        table_flattening = kwargs.get("table_flattening", True)

        parent_config = ChunkingConfig(
            chunk_size=parent_chunk_size,
            chunk_overlap=0  # Parents don't overlap
        )
        child_config = ChunkingConfig(
            chunk_size=child_chunk_size,
            chunk_overlap=child_chunk_overlap
        )

        table_preprocessor = None
        if table_flattening:
            from src.infrastructure.chunking.table_flattening.preprocessor import (
                TableFlatteningPreprocessor,
            )
            from src.infrastructure.chunking.table_flattening.rule_based_generator import (
                RuleBasedTableContentGenerator,
            )

            table_preprocessor = TableFlatteningPreprocessor(
                RuleBasedTableContentGenerator()
            )

        return ParentChildStrategy(
            parent_config=parent_config,
            child_config=child_config,
            table_preprocessor=table_preprocessor,
        )

    @classmethod
    def _create_semantic_strategy(cls, **kwargs) -> SemanticStrategy:
        chunk_size = kwargs.get("chunk_size", cls.DEFAULT_SEMANTIC_MAX_SIZE)
        min_chunk_size = kwargs.get("min_chunk_size", cls.DEFAULT_SEMANTIC_MIN_SIZE)
        config = ChunkingConfig(chunk_size=chunk_size, chunk_overlap=0)
        return SemanticStrategy(config, min_chunk_size=min_chunk_size)

    DEFAULT_SECTION_AWARE_SIZE = 2000
    DEFAULT_SECTION_AWARE_OVERLAP = 200
    DEFAULT_SECTION_AWARE_MIN = 100

    @classmethod
    def _create_section_aware_strategy(
        cls, **kwargs
    ) -> SectionAwareChunkingStrategy:
        chunk_size = kwargs.get("chunk_size", cls.DEFAULT_SECTION_AWARE_SIZE)
        chunk_overlap = kwargs.get("chunk_overlap", cls.DEFAULT_SECTION_AWARE_OVERLAP)
        min_chunk_size = kwargs.get("min_chunk_size", cls.DEFAULT_SECTION_AWARE_MIN)
        config = ChunkingConfig(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        return SectionAwareChunkingStrategy(config, min_chunk_size=min_chunk_size)

    DEFAULT_CLAUSE_PARENT_SIZE = 2000
    DEFAULT_CLAUSE_CHILD_SIZE = 500
    DEFAULT_CLAUSE_CHILD_OVERLAP = 50

    @classmethod
    def _create_clause_aware_strategy(
        cls, **kwargs
    ) -> ClauseAwareStrategy:
        """Create ClauseAwareStrategy (clause-aware-chunking Design §6.1).

        kwargs:
            parent_patterns, child_patterns: 정규식 문자열 목록 (priority 정렬 완료).
            parent_chunk_size, chunk_size, chunk_overlap: 토큰 파라미터.
        """
        parent_patterns = kwargs.get("parent_patterns", [])
        child_patterns = kwargs.get("child_patterns", [])
        parent_chunk_size = kwargs.get(
            "parent_chunk_size", cls.DEFAULT_CLAUSE_PARENT_SIZE
        )
        chunk_size = kwargs.get("chunk_size", cls.DEFAULT_CLAUSE_CHILD_SIZE)
        chunk_overlap = kwargs.get(
            "chunk_overlap", cls.DEFAULT_CLAUSE_CHILD_OVERLAP
        )

        compiled_parents = [
            re.compile(p, re.MULTILINE) for p in parent_patterns
        ]
        compiled_children = [
            re.compile(p, re.MULTILINE) for p in child_patterns
        ]
        parent_config = ChunkingConfig(
            chunk_size=parent_chunk_size, chunk_overlap=0
        )
        child_config = ChunkingConfig(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
        return ClauseAwareStrategy(
            parent_patterns=compiled_parents,
            child_patterns=compiled_children,
            parent_config=parent_config,
            child_config=child_config,
        )

    @classmethod
    def list_strategies(cls) -> List[str]:
        """List all available strategy type names.

        Returns:
            List of strategy type string values.
        """
        return [strategy.value for strategy in StrategyType]
