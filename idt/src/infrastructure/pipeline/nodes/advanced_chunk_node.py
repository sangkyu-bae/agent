from src.infrastructure.chunking.chunking_factory import ChunkingStrategyFactory
from src.infrastructure.pipeline.state.advanced_pipeline_state import AdvancedPipelineState


async def advanced_chunk_node(state: AdvancedPipelineState) -> dict:
    documents = state.get("preprocessed_documents") or state.get("parsed_documents", [])
    if not documents:
        return {
            "status": "failed",
            "errors": state["errors"] + ["No documents to chunk"],
        }

    try:
        strategy = ChunkingStrategyFactory.create_strategy(
            state["chunking_strategy"],
            chunk_size=state["chunk_size"],
            chunk_overlap=state["chunk_overlap"],
            table_flattening=False,
        )
        chunked = strategy.chunk(documents)

        if not chunked:
            return {
                "status": "failed",
                "errors": state["errors"] + ["No chunks produced"],
            }

        document_id = state.get("document_id", "")
        for chunk in chunked:
            chunk.metadata["document_id"] = document_id

        return {
            "chunked_documents": chunked,
            "chunk_count": len(chunked),
            "status": "chunking",
        }
    except Exception as e:
        return {
            "status": "failed",
            "errors": state["errors"] + [f"Chunking failed: {str(e)}"],
        }
