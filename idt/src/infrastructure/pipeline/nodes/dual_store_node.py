import asyncio
import json
import uuid

from src.domain.elasticsearch.schemas import ESDocument
from src.domain.elasticsearch.interfaces import ElasticsearchRepositoryInterface
from src.domain.vector.entities import Document as VecDoc
from src.domain.vector.interfaces import EmbeddingInterface, VectorStoreInterface
from src.infrastructure.elasticsearch.es_index_mappings import (
    DOCUMENTS_INDEX_MAPPINGS,
    DOCUMENTS_INDEX_SETTINGS,
)
from src.infrastructure.pipeline.state.advanced_pipeline_state import AdvancedPipelineState


async def dual_store_node(
    state: AdvancedPipelineState,
    embedding: EmbeddingInterface,
    vectorstore: VectorStoreInterface,
    es_repo: ElasticsearchRepositoryInterface,
) -> dict:
    chunks = state.get("chunked_documents", [])
    if not chunks:
        return {
            "status": "failed",
            "errors": state["errors"] + ["No chunks to store"],
        }

    collection_name = state.get("collection_name", "documents")
    request_id = state.get("request_id", "")
    morph_keywords_per_chunk = state.get("morph_keywords_per_chunk", [])
    document_id = state.get("document_id", "")
    user_id = state.get("user_id", "")

    try:
        texts = [c.page_content for c in chunks]
        vectors = await embedding.embed_documents(texts)

        vec_docs: list[VecDoc] = []
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            chunk_id = chunk.metadata.get("chunk_id") or str(uuid.uuid4())
            metadata = {k: str(v) for k, v in chunk.metadata.items()}
            metadata["user_id"] = user_id
            metadata["document_id"] = document_id
            metadata["collection_name"] = collection_name
            if i < len(morph_keywords_per_chunk):
                metadata["morph_keywords"] = json.dumps(
                    morph_keywords_per_chunk[i], ensure_ascii=False
                )
            vec_docs.append(VecDoc(id=None, content=chunk.page_content, vector=vector, metadata=metadata))

        es_index = f"docs_{collection_name}"
        es_docs: list[ESDocument] = []
        for i, chunk in enumerate(chunks):
            chunk_id = chunk.metadata.get("chunk_id") or str(uuid.uuid4())
            body: dict = {
                "content": chunk.page_content,
                "chunk_id": chunk_id,
                "chunk_type": chunk.metadata.get("chunk_type", "full"),
                "chunk_index": chunk.metadata.get("chunk_index", i),
                "total_chunks": chunk.metadata.get("total_chunks", len(chunks)),
                "document_id": document_id,
                "user_id": user_id,
                "collection_name": collection_name,
            }
            if i < len(morph_keywords_per_chunk):
                body["morph_keywords"] = morph_keywords_per_chunk[i]
            if "parent_id" in chunk.metadata:
                body["parent_id"] = chunk.metadata["parent_id"]
            es_docs.append(ESDocument(id=chunk_id, body=body, index=es_index))

        await es_repo.ensure_index_exists(
            index=es_index,
            mappings=DOCUMENTS_INDEX_MAPPINGS,
            settings=DOCUMENTS_INDEX_SETTINGS,
        )

        qdrant_task = vectorstore.add_documents(vec_docs)
        es_task = es_repo.bulk_index(es_docs, request_id)
        qdrant_ids, es_count = await asyncio.gather(qdrant_task, es_task)

        qdrant_id_strings = [doc_id.value for doc_id in qdrant_ids]

        return {
            "qdrant_stored_ids": qdrant_id_strings,
            "qdrant_stored_count": len(qdrant_id_strings),
            "es_stored_count": es_count,
            "es_index_name": es_index,
            "status": "storing",
        }
    except Exception as e:
        return {
            "status": "failed",
            "errors": state["errors"] + [f"Dual store failed: {str(e)}"],
        }
