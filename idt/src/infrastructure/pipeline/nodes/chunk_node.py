"""Chunk node for document processing pipeline."""
from typing import List

from langchain_core.documents import Document

from src.domain.chunking.interfaces import ChunkingStrategy
from src.domain.pipeline.state.pipeline_state import PipelineState


async def chunk_node(
    state: PipelineState,
    chunking_strategy: ChunkingStrategy,
) -> PipelineState:
    """Chunk documents based on category configuration.

    Args:
        state: Current pipeline state with parsed_documents and category.
        chunking_strategy: Chunking strategy to use.

    Returns:
        Updated pipeline state with chunked documents.
    """
    try:
        category = state.get("category")

        if category is None:
            return {
                **state,
                "status": "failed",
                "errors": state["errors"] + ["No category set for chunking"],
            }

        documents = state.get("parsed_documents", [])

        # Perform chunking
        chunked_documents: List[Document] = chunking_strategy.chunk(documents)

        if not chunked_documents:
            return {
                **state,
                "status": "failed",
                "errors": state["errors"] + ["No chunks produced from documents"],
            }

        # Add category and document_id metadata to all chunks
        document_id = state.get("document_id", "")
        category_value = category.value if hasattr(category, "value") else str(category)

        for chunk in chunked_documents:
            chunk.metadata["category"] = category_value
            chunk.metadata["document_id"] = document_id

        # Record chunking configuration used
        chunking_config_used = {
            "chunk_size": chunking_strategy.get_chunk_size(),
            "strategy": chunking_strategy.get_strategy_name(),
            "category": category_value,
        }

        return {
            **state,
            "chunked_documents": chunked_documents,
            "chunk_count": len(chunked_documents),
            "chunking_config_used": chunking_config_used,
            "status": "chunking",
        }

    except Exception as e:
        return {
            **state,
            "status": "failed",
            "errors": state["errors"] + [f"Chunking failed: {str(e)}"],
        }
