from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.documents import Document

from src.domain.vector.value_objects import DocumentId
from src.infrastructure.pipeline.nodes.dual_store_node import dual_store_node
from src.infrastructure.pipeline.state.advanced_pipeline_state import (
    create_advanced_initial_state,
)


def _make_state(**overrides):
    state = create_advanced_initial_state(
        file_bytes=b"pdf", filename="t.pdf", user_id="u", request_id="r",
    )
    state["chunked_documents"] = [
        Document(page_content="chunk 1", metadata={"chunk_id": "c1", "chunk_type": "child"}),
        Document(page_content="chunk 2", metadata={"chunk_id": "c2", "chunk_type": "child"}),
    ]
    state["document_id"] = "doc-123"
    state["morph_keywords_per_chunk"] = [["금융", "시장"], ["대출", "금리"]]
    state.update(overrides)
    return state


def _make_deps(qdrant_ids=None, es_count=2):
    embedding = AsyncMock()
    embedding.embed_documents.return_value = [[0.1, 0.2], [0.3, 0.4]]

    vectorstore = AsyncMock()
    ids = qdrant_ids or [DocumentId(value="id-1"), DocumentId(value="id-2")]
    vectorstore.add_documents.return_value = ids

    es_repo = AsyncMock()
    es_repo.bulk_index.return_value = es_count
    es_repo.ensure_index_exists.return_value = None

    return embedding, vectorstore, es_repo


class TestDualStoreNode:

    @pytest.mark.asyncio
    async def test_happy_path(self):
        state = _make_state()
        embedding, vectorstore, es_repo = _make_deps()

        result = await dual_store_node(state, embedding, vectorstore, es_repo)

        assert result["qdrant_stored_count"] == 2
        assert result["es_stored_count"] == 2
        assert result["es_index_name"] == "docs_documents"
        assert result["status"] == "storing"
        assert len(result["qdrant_stored_ids"]) == 2

    @pytest.mark.asyncio
    async def test_es_index_name_from_collection(self):
        state = _make_state(collection_name="financial_docs")
        embedding, vectorstore, es_repo = _make_deps()

        result = await dual_store_node(state, embedding, vectorstore, es_repo)

        assert result["es_index_name"] == "docs_financial_docs"

    @pytest.mark.asyncio
    async def test_ensure_index_called(self):
        state = _make_state()
        embedding, vectorstore, es_repo = _make_deps()

        await dual_store_node(state, embedding, vectorstore, es_repo)

        es_repo.ensure_index_exists.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_chunks_fails(self):
        state = _make_state(chunked_documents=[])
        embedding, vectorstore, es_repo = _make_deps()

        result = await dual_store_node(state, embedding, vectorstore, es_repo)

        assert result["status"] == "failed"
        assert any("No chunks to store" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_exception_fails(self):
        state = _make_state()
        embedding = AsyncMock()
        embedding.embed_documents.side_effect = RuntimeError("embedding error")
        vectorstore = AsyncMock()
        es_repo = AsyncMock()

        result = await dual_store_node(state, embedding, vectorstore, es_repo)

        assert result["status"] == "failed"
        assert any("Dual store failed" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_morph_keywords_in_metadata(self):
        state = _make_state()
        embedding, vectorstore, es_repo = _make_deps()

        await dual_store_node(state, embedding, vectorstore, es_repo)

        vec_docs = vectorstore.add_documents.call_args[0][0]
        assert "morph_keywords" in vec_docs[0].metadata
