"""Store node for document processing pipeline."""
from typing import List

from langchain_core.documents import Document as LCDocument

from src.domain.vector.interfaces import VectorStoreInterface, EmbeddingInterface
from src.domain.vector.entities import Document as VectorDocument
from src.domain.pipeline.state.pipeline_state import PipelineState


async def store_node(
    state: PipelineState,
    vectorstore: VectorStoreInterface,
    embedding: EmbeddingInterface,
    collection_name: str,
) -> PipelineState:
    """Store chunked documents in vector store.

    Args:
        state: Current pipeline state with chunked_documents.
        vectorstore: Vector store implementation.
        embedding: Embedding provider.
        collection_name: Name of collection to store in.

    Returns:
        Updated pipeline state with stored IDs.
    """
    try:
        chunked_documents: List[LCDocument] = state.get("chunked_documents", [])

        if not chunked_documents:
            return {
                **state,
                "status": "failed",
                "errors": state["errors"] + ["No chunks to store"],
            }

        # Extract texts for embedding
        texts = [doc.page_content for doc in chunked_documents]

        # Generate embeddings
        vectors = await embedding.embed_documents(texts)

        # Convert to VectorDocument format with metadata
        user_id = state.get("user_id", "")
        documents_to_store: List[VectorDocument] = []

        for i, (chunk, vector) in enumerate(zip(chunked_documents, vectors)):
            metadata = dict(chunk.metadata)
            metadata["user_id"] = user_id

            doc = VectorDocument(
                id=None,
                content=chunk.page_content,
                vector=vector,
                metadata=metadata,
            )
            documents_to_store.append(doc)

        # Store in vector store
        stored_ids = await vectorstore.add_documents(documents_to_store)

        # Convert DocumentId to strings (access .value attribute)
        stored_id_strings = [doc_id.value for doc_id in stored_ids]

        return {
            **state,
            "stored_ids": stored_id_strings,
            "collection_name": collection_name,
            "status": "storing",
        }

    except Exception as e:
        return {
            **state,
            "status": "failed",
            "errors": state["errors"] + [f"Store failed: {str(e)}"],
        }
