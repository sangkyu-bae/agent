from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from src.infrastructure.pipeline.nodes.advanced_chunk_node import advanced_chunk_node
from src.infrastructure.pipeline.state.advanced_pipeline_state import (
    create_advanced_initial_state,
)


def _make_state(**overrides):
    state = create_advanced_initial_state(
        file_bytes=b"pdf", filename="t.pdf", user_id="u", request_id="r",
    )
    state["preprocessed_documents"] = [
        Document(page_content="content chunk 1", metadata={"chunk_index": 0}),
        Document(page_content="content chunk 2", metadata={"chunk_index": 1}),
    ]
    state["document_id"] = "doc-123"
    state.update(overrides)
    return state


class TestAdvancedChunkNode:

    @pytest.mark.asyncio
    async def test_happy_path(self):
        state = _make_state()
        chunked = [
            Document(page_content="c1", metadata={}),
            Document(page_content="c2", metadata={}),
            Document(page_content="c3", metadata={}),
        ]

        with patch(
            "src.infrastructure.pipeline.nodes.advanced_chunk_node.ChunkingStrategyFactory"
        ) as mock_factory:
            mock_strategy = MagicMock()
            mock_strategy.chunk.return_value = chunked
            mock_factory.create_strategy.return_value = mock_strategy

            result = await advanced_chunk_node(state)

        assert result["chunk_count"] == 3
        assert result["status"] == "chunking"
        for doc in result["chunked_documents"]:
            assert doc.metadata["document_id"] == "doc-123"

    @pytest.mark.asyncio
    async def test_uses_preprocessed_over_parsed(self):
        state = _make_state()
        state["parsed_documents"] = [Document(page_content="parsed", metadata={})]

        with patch(
            "src.infrastructure.pipeline.nodes.advanced_chunk_node.ChunkingStrategyFactory"
        ) as mock_factory:
            mock_strategy = MagicMock()
            mock_strategy.chunk.return_value = [
                Document(page_content="from preprocessed", metadata={})
            ]
            mock_factory.create_strategy.return_value = mock_strategy

            result = await advanced_chunk_node(state)

        call_docs = mock_strategy.chunk.call_args[0][0]
        assert call_docs[0].page_content == "content chunk 1"

    @pytest.mark.asyncio
    async def test_falls_back_to_parsed(self):
        state = _make_state(preprocessed_documents=[])
        state["parsed_documents"] = [Document(page_content="parsed", metadata={})]

        with patch(
            "src.infrastructure.pipeline.nodes.advanced_chunk_node.ChunkingStrategyFactory"
        ) as mock_factory:
            mock_strategy = MagicMock()
            mock_strategy.chunk.return_value = [
                Document(page_content="c", metadata={})
            ]
            mock_factory.create_strategy.return_value = mock_strategy

            result = await advanced_chunk_node(state)

        call_docs = mock_strategy.chunk.call_args[0][0]
        assert call_docs[0].page_content == "parsed"

    @pytest.mark.asyncio
    async def test_no_documents_fails(self):
        state = _make_state(preprocessed_documents=[], parsed_documents=[])

        result = await advanced_chunk_node(state)

        assert result["status"] == "failed"
        assert any("No documents to chunk" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_empty_chunks_fails(self):
        state = _make_state()

        with patch(
            "src.infrastructure.pipeline.nodes.advanced_chunk_node.ChunkingStrategyFactory"
        ) as mock_factory:
            mock_strategy = MagicMock()
            mock_strategy.chunk.return_value = []
            mock_factory.create_strategy.return_value = mock_strategy

            result = await advanced_chunk_node(state)

        assert result["status"] == "failed"
        assert any("No chunks produced" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_exception_fails(self):
        state = _make_state()

        with patch(
            "src.infrastructure.pipeline.nodes.advanced_chunk_node.ChunkingStrategyFactory"
        ) as mock_factory:
            mock_factory.create_strategy.side_effect = RuntimeError("bad strategy")

            result = await advanced_chunk_node(state)

        assert result["status"] == "failed"
        assert any("Chunking failed" in e for e in result["errors"])
