from unittest.mock import MagicMock

import pytest
from langchain_core.documents import Document

from src.infrastructure.pipeline.nodes.advanced_parse_node import advanced_parse_node
from src.infrastructure.pipeline.state.advanced_pipeline_state import (
    create_advanced_initial_state,
)


def _make_state_after_route(**overrides):
    state = create_advanced_initial_state(
        file_bytes=b"pdf-content", filename="doc.pdf",
        user_id="u1", request_id="r1",
    )
    state["routed_parser_type"] = "pymupdf"
    state.update(overrides)
    return state


def _make_mock_parser(documents=None, side_effect=None):
    parser = MagicMock()
    if side_effect:
        parser.parse_bytes.side_effect = side_effect
    else:
        if documents is None:
            documents = [
                Document(
                    page_content="Page 1 content",
                    metadata={"document_id": "doc-123", "page": 1},
                ),
            ]
        parser.parse_bytes.return_value = documents
    return parser


class TestAdvancedParseNode:

    @pytest.mark.asyncio
    async def test_happy_path(self):
        state = _make_state_after_route()
        parsers = {"pymupdf": _make_mock_parser()}

        result = await advanced_parse_node(state, parsers)

        assert len(result["parsed_documents"]) == 1
        assert result["document_id"] == "doc-123"
        assert result["total_pages"] == 1
        assert result["status"] == "parsing"

    @pytest.mark.asyncio
    async def test_uses_routed_parser(self):
        state = _make_state_after_route(routed_parser_type="pymupdf4llm")
        pymupdf = _make_mock_parser()
        pymupdf4llm = _make_mock_parser(
            documents=[
                Document(page_content="llm output", metadata={"document_id": "d2"}),
            ]
        )
        parsers = {"pymupdf": pymupdf, "pymupdf4llm": pymupdf4llm}

        result = await advanced_parse_node(state, parsers)

        pymupdf.parse_bytes.assert_not_called()
        pymupdf4llm.parse_bytes.assert_called_once()
        assert result["document_id"] == "d2"

    @pytest.mark.asyncio
    async def test_unknown_parser_falls_back_to_pymupdf(self):
        state = _make_state_after_route(routed_parser_type="unknown")
        pymupdf = _make_mock_parser()
        parsers = {"pymupdf": pymupdf}

        result = await advanced_parse_node(state, parsers)

        pymupdf.parse_bytes.assert_called_once()
        assert result["status"] == "parsing"

    @pytest.mark.asyncio
    async def test_no_parser_available_fails(self):
        state = _make_state_after_route(routed_parser_type="nonexistent")
        parsers = {}

        result = await advanced_parse_node(state, parsers)

        assert result["status"] == "failed"
        assert any("No parser available" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_parser_exception_fails(self):
        state = _make_state_after_route()
        parsers = {"pymupdf": _make_mock_parser(side_effect=RuntimeError("parse error"))}

        result = await advanced_parse_node(state, parsers)

        assert result["status"] == "failed"
        assert any("Parse failed" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_empty_documents_fails(self):
        state = _make_state_after_route()
        parsers = {"pymupdf": _make_mock_parser(documents=[])}

        result = await advanced_parse_node(state, parsers)

        assert result["status"] == "failed"
        assert any("No documents parsed" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_document_id_empty_when_no_metadata(self):
        state = _make_state_after_route()
        doc = Document(page_content="content", metadata={})
        parsers = {"pymupdf": _make_mock_parser(documents=[doc])}

        result = await advanced_parse_node(state, parsers)

        assert result["document_id"] == ""
