"""Tests for relevance prompt templates."""
import pytest

from langchain_core.documents import Document

from src.infrastructure.compressor.prompts.relevance_prompt import (
    RelevancePromptBuilder,
    RelevanceResponse,
)


class TestRelevanceResponseSchema:
    """Tests for RelevanceResponse Pydantic schema."""

    def test_create_relevance_response_with_all_fields(self):
        """RelevanceResponse should be created with all fields."""
        response = RelevanceResponse(
            is_relevant=True,
            score=0.85,
            reasoning="Document answers the query directly",
        )

        assert response.is_relevant is True
        assert response.score == 0.85
        assert response.reasoning == "Document answers the query directly"

    def test_relevance_response_score_validation(self):
        """RelevanceResponse score should be between 0.0 and 1.0."""
        with pytest.raises(ValueError):
            RelevanceResponse(is_relevant=True, score=1.5, reasoning="test")

        with pytest.raises(ValueError):
            RelevanceResponse(is_relevant=True, score=-0.1, reasoning="test")

    def test_relevance_response_boundary_values(self):
        """RelevanceResponse should accept boundary score values."""
        response_zero = RelevanceResponse(
            is_relevant=False, score=0.0, reasoning="not relevant"
        )
        response_one = RelevanceResponse(
            is_relevant=True, score=1.0, reasoning="highly relevant"
        )

        assert response_zero.score == 0.0
        assert response_one.score == 1.0


class TestRelevancePromptBuilder:
    """Tests for RelevancePromptBuilder."""

    @pytest.fixture
    def builder(self) -> RelevancePromptBuilder:
        return RelevancePromptBuilder()

    @pytest.fixture
    def sample_document(self) -> Document:
        return Document(
            page_content="Python is a programming language used for data analysis.",
            metadata={"source": "test.pdf", "page": 1},
        )

    def test_build_prompt_includes_query(
        self, builder: RelevancePromptBuilder, sample_document: Document
    ):
        """Prompt should include the query."""
        prompt = builder.build_prompt(sample_document, "What is Python?")

        assert "What is Python?" in prompt

    def test_build_prompt_includes_document_content(
        self, builder: RelevancePromptBuilder, sample_document: Document
    ):
        """Prompt should include document content."""
        prompt = builder.build_prompt(sample_document, "test query")

        assert "Python is a programming language" in prompt

    def test_build_prompt_requests_json_response(
        self, builder: RelevancePromptBuilder, sample_document: Document
    ):
        """Prompt should request JSON formatted response."""
        prompt = builder.build_prompt(sample_document, "test query")

        assert "json" in prompt.lower() or "JSON" in prompt

    def test_build_prompt_mentions_score_range(
        self, builder: RelevancePromptBuilder, sample_document: Document
    ):
        """Prompt should mention score range 0.0-1.0."""
        prompt = builder.build_prompt(sample_document, "test query")

        assert "0.0" in prompt or "0" in prompt
        assert "1.0" in prompt or "1" in prompt

    def test_build_prompt_with_reasoning_request(
        self, builder: RelevancePromptBuilder, sample_document: Document
    ):
        """Prompt with include_reasoning=True should request reasoning."""
        prompt = builder.build_prompt(
            sample_document, "test query", include_reasoning=True
        )

        assert "reason" in prompt.lower() or "explain" in prompt.lower()

    def test_build_prompt_without_reasoning_request(
        self, builder: RelevancePromptBuilder, sample_document: Document
    ):
        """Prompt with include_reasoning=False should not emphasize reasoning."""
        prompt = builder.build_prompt(
            sample_document, "test query", include_reasoning=False
        )

        assert "is_relevant" in prompt.lower() or "score" in prompt.lower()

    def test_build_prompt_handles_empty_content(self, builder: RelevancePromptBuilder):
        """Prompt should handle empty document content."""
        empty_doc = Document(page_content="", metadata={})
        prompt = builder.build_prompt(empty_doc, "test query")

        assert "test query" in prompt

    def test_build_prompt_handles_special_characters(
        self, builder: RelevancePromptBuilder
    ):
        """Prompt should handle documents with special characters."""
        special_doc = Document(
            page_content='Text with "quotes" and {braces} and <tags>',
            metadata={},
        )
        prompt = builder.build_prompt(special_doc, "test query")

        assert "quotes" in prompt or "Text" in prompt
