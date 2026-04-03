"""Pipeline configuration."""
from src.domain.pipeline.config.chunking_strategy_config import (
    CATEGORY_CHUNKING_CONFIG,
    get_chunking_config,
)

__all__ = ["CATEGORY_CHUNKING_CONFIG", "get_chunking_config"]
