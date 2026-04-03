"""Chunking strategy configuration mapping by document category."""
from typing import Dict

from src.domain.chunking.value_objects import ChunkingConfig
from src.domain.pipeline.enums.document_category import DocumentCategory


CATEGORY_CHUNKING_CONFIG: Dict[DocumentCategory, ChunkingConfig] = {
    DocumentCategory.IT_SYSTEM: ChunkingConfig(
        chunk_size=2000,
        chunk_overlap=200,
    ),
    DocumentCategory.HR: ChunkingConfig(
        chunk_size=400,
        chunk_overlap=100,
    ),
    DocumentCategory.LOAN_FINANCE: ChunkingConfig(
        chunk_size=800,
        chunk_overlap=100,
    ),
    DocumentCategory.SECURITY_ACCESS: ChunkingConfig(
        chunk_size=600,
        chunk_overlap=100,
    ),
    DocumentCategory.ACCOUNTING_LEGAL: ChunkingConfig(
        chunk_size=1000,
        chunk_overlap=150,
    ),
    DocumentCategory.GENERAL: ChunkingConfig(
        chunk_size=1000,
        chunk_overlap=100,
    ),
}


def get_chunking_config(category: DocumentCategory) -> ChunkingConfig:
    """Get chunking configuration for a document category.

    Args:
        category: Document category to get config for.

    Returns:
        ChunkingConfig for the specified category.
    """
    return CATEGORY_CHUNKING_CONFIG[category]
