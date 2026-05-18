from unittest.mock import MagicMock

import pytest
from langchain_core.documents import Document

from src.domain.chunking.table_content_generator import PreprocessResult
from src.infrastructure.pipeline.nodes.table_preprocess_node import (
    table_preprocess_node,
)
from src.infrastructure.pipeline.state.advanced_pipeline_state import (
    create_advanced_initial_state,
)


def _make_state(**overrides):
    state = create_advanced_initial_state(
        file_bytes=b"pdf", filename="t.pdf", user_id="u", request_id="r",
    )
    state["parsed_documents"] = [
        Document(
            page_content="| col1 | col2 |\n|---|---|\n| a | b |",
            metadata={"section_title": "Table Section"},
        ),
    ]
    state.update(overrides)
    return state


def _make_preprocessor(table_count=1, side_effect=None):
    preprocessor = MagicMock()
    if side_effect:
        preprocessor.process.side_effect = side_effect
    else:
        preprocessor.process.return_value = PreprocessResult(
            parent_text="original table",
            child_text="col1 is a, col2 is b",
            table_count=table_count,
            metadata={"rows": 1, "cols": 2} if table_count > 0 else None,
        )
    return preprocessor


class TestTablePreprocessNode:

    @pytest.mark.asyncio
    async def test_happy_path(self):
        state = _make_state()
        preprocessor = _make_preprocessor(table_count=1)

        result = await table_preprocess_node(state, preprocessor)

        assert result["table_flattened"] is True
        assert result["table_count"] == 1
        assert len(result["preprocessed_documents"]) == 1

    @pytest.mark.asyncio
    async def test_no_tables_found(self):
        state = _make_state()
        preprocessor = _make_preprocessor(table_count=0)

        result = await table_preprocess_node(state, preprocessor)

        assert result["table_flattened"] is False
        assert result["table_count"] == 0

    @pytest.mark.asyncio
    async def test_disabled_passes_through(self):
        state = _make_state(enable_table_flattening=False)
        preprocessor = _make_preprocessor()

        result = await table_preprocess_node(state, preprocessor)

        assert result["table_flattened"] is False
        assert result["table_count"] == 0
        assert len(result["preprocessed_documents"]) == 1
        preprocessor.process.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_documents_fails(self):
        state = _make_state(parsed_documents=[])
        preprocessor = _make_preprocessor()

        result = await table_preprocess_node(state, preprocessor)

        assert result["status"] == "failed"

    @pytest.mark.asyncio
    async def test_exception_preserves_original(self):
        state = _make_state()
        preprocessor = _make_preprocessor(side_effect=RuntimeError("table error"))

        result = await table_preprocess_node(state, preprocessor)

        assert result["table_flattened"] is False
        assert len(result["preprocessed_documents"]) == 1
        assert any("Table preprocessing failed" in e for e in result["errors"])
