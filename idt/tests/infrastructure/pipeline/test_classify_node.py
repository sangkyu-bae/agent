"""Tests for classify node."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.documents import Document

from src.infrastructure.pipeline.nodes.classify_node import classify_node
from src.domain.pipeline.state.pipeline_state import PipelineState
from src.domain.pipeline.enums.document_category import DocumentCategory
from src.domain.pipeline.schemas.classification_schema import ClassificationResult
from src.domain.compressor.interfaces.llm_provider_interface import LLMProviderInterface


def create_state_after_parsing(
    parsed_documents: list = None,
    total_pages: int = 3,
) -> PipelineState:
    """Create pipeline state after parsing step."""
    if parsed_documents is None:
        parsed_documents = [
            Document(page_content=f"Page {i} content", metadata={"page": i})
            for i in range(1, total_pages + 1)
        ]
    return {
        "file_path": "/path/to/doc.pdf",
        "file_bytes": None,
        "filename": "doc.pdf",
        "user_id": "user123",
        "parsed_documents": parsed_documents,
        "total_pages": len(parsed_documents),
        "document_id": "abc123_doc",
        "category": None,
        "category_confidence": 0.0,
        "classification_reasoning": "",
        "sample_pages": [],
        "chunked_documents": [],
        "chunk_count": 0,
        "chunking_config_used": {},
        "stored_ids": [],
        "collection_name": "",
        "processing_time_ms": 0,
        "errors": [],
        "status": "parsing",
    }


class TestClassifyNodeSuccess:
    """Test classify node successful scenarios."""

    @pytest.mark.asyncio
    async def test_classification_returns_valid_category(self):
        """Test classification returns valid category."""
        mock_llm = AsyncMock(spec=LLMProviderInterface)
        mock_llm.generate_structured.return_value = ClassificationResult(
            category=DocumentCategory.IT_SYSTEM,
            confidence=0.95,
            reasoning="Technical documentation with system specs",
        )

        state = create_state_after_parsing()
        result = await classify_node(state, mock_llm)

        assert result["category"] == DocumentCategory.IT_SYSTEM
        assert result["category_confidence"] == 0.95
        assert result["classification_reasoning"] == "Technical documentation with system specs"
        assert result["status"] == "classifying"

    @pytest.mark.asyncio
    async def test_sample_pages_populated(self):
        """Test sample_pages is populated in state."""
        mock_llm = AsyncMock(spec=LLMProviderInterface)
        mock_llm.generate_structured.return_value = ClassificationResult(
            category=DocumentCategory.HR,
            confidence=0.88,
            reasoning="HR policy document",
        )

        docs = [
            Document(page_content="First page content", metadata={"page": 1}),
            Document(page_content="Middle page content", metadata={"page": 2}),
            Document(page_content="Last page content", metadata={"page": 3}),
        ]
        state = create_state_after_parsing(parsed_documents=docs)
        result = await classify_node(state, mock_llm)

        assert len(result["sample_pages"]) == 3
        assert "First page" in result["sample_pages"][0]

    @pytest.mark.asyncio
    async def test_all_categories_accepted(self):
        """Test all document categories are accepted."""
        for category in DocumentCategory:
            mock_llm = AsyncMock(spec=LLMProviderInterface)
            mock_llm.generate_structured.return_value = ClassificationResult(
                category=category,
                confidence=0.9,
                reasoning=f"Classified as {category.value}",
            )

            state = create_state_after_parsing()
            result = await classify_node(state, mock_llm)

            assert result["category"] == category


class TestClassifyNodeFallback:
    """Test classify node fallback behavior."""

    @pytest.mark.asyncio
    async def test_low_confidence_falls_back_to_general(self):
        """Test low confidence (< 0.5) falls back to GENERAL."""
        mock_llm = AsyncMock(spec=LLMProviderInterface)
        mock_llm.generate_structured.return_value = ClassificationResult(
            category=DocumentCategory.IT_SYSTEM,
            confidence=0.3,  # Low confidence
            reasoning="Uncertain classification",
        )

        state = create_state_after_parsing()
        result = await classify_node(state, mock_llm)

        assert result["category"] == DocumentCategory.GENERAL
        assert result["category_confidence"] == 0.3

    @pytest.mark.asyncio
    async def test_confidence_threshold_0_5(self):
        """Test confidence exactly at 0.5 is accepted."""
        mock_llm = AsyncMock(spec=LLMProviderInterface)
        mock_llm.generate_structured.return_value = ClassificationResult(
            category=DocumentCategory.LOAN_FINANCE,
            confidence=0.5,
            reasoning="Borderline confidence",
        )

        state = create_state_after_parsing()
        result = await classify_node(state, mock_llm)

        assert result["category"] == DocumentCategory.LOAN_FINANCE


class TestClassifyNodeErrorHandling:
    """Test classify node error handling."""

    @pytest.mark.asyncio
    async def test_llm_error_sets_failed_status(self):
        """Test LLM error sets status to failed."""
        mock_llm = AsyncMock(spec=LLMProviderInterface)
        mock_llm.generate_structured.side_effect = Exception("LLM API error")

        state = create_state_after_parsing()
        result = await classify_node(state, mock_llm)

        assert result["status"] == "failed"
        assert len(result["errors"]) > 0
        assert "Classification failed" in result["errors"][-1]

    @pytest.mark.asyncio
    async def test_empty_documents_sets_failed(self):
        """Test empty documents sets failed status."""
        mock_llm = AsyncMock(spec=LLMProviderInterface)

        state = create_state_after_parsing(parsed_documents=[])
        result = await classify_node(state, mock_llm)

        assert result["status"] == "failed"
        assert len(result["errors"]) > 0
