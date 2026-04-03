"""Tests for classification prompt builder."""
import pytest
from langchain_core.documents import Document

from src.infrastructure.pipeline.prompts.classification_prompt import (
    extract_sample_pages,
    build_classification_prompt,
    CLASSIFICATION_SYSTEM_PROMPT,
)
from src.domain.pipeline.enums.document_category import DocumentCategory


class TestExtractSamplePages:
    """Test extract_sample_pages function."""

    def test_single_page_returns_first(self):
        """Test 1 page document returns [first]."""
        docs = [Document(page_content="Page 1 content", metadata={"page": 1})]
        samples = extract_sample_pages(docs)
        assert len(samples) == 1
        assert "Page 1 content" in samples[0]

    def test_two_pages_returns_first_and_last(self):
        """Test 2 page document returns [first, last]."""
        docs = [
            Document(page_content="First page", metadata={"page": 1}),
            Document(page_content="Last page", metadata={"page": 2}),
        ]
        samples = extract_sample_pages(docs)
        assert len(samples) == 2
        assert "First page" in samples[0]
        assert "Last page" in samples[1]

    def test_three_pages_returns_first_middle_last(self):
        """Test 3+ page document returns [first, middle, last]."""
        docs = [
            Document(page_content="First page content", metadata={"page": 1}),
            Document(page_content="Middle page content", metadata={"page": 2}),
            Document(page_content="Last page content", metadata={"page": 3}),
        ]
        samples = extract_sample_pages(docs)
        assert len(samples) == 3
        assert "First page" in samples[0]
        assert "Middle page" in samples[1]
        assert "Last page" in samples[2]

    def test_five_pages_returns_first_middle_last(self):
        """Test 5 page document returns [first, middle, last]."""
        docs = [
            Document(page_content=f"Page {i} content", metadata={"page": i})
            for i in range(1, 6)
        ]
        samples = extract_sample_pages(docs)
        assert len(samples) == 3
        assert "Page 1" in samples[0]
        assert "Page 3" in samples[1]  # Middle page
        assert "Page 5" in samples[2]

    def test_empty_documents_returns_empty(self):
        """Test empty documents returns empty list."""
        samples = extract_sample_pages([])
        assert samples == []


class TestBuildClassificationPrompt:
    """Test build_classification_prompt function."""

    def test_prompt_contains_sample_pages(self):
        """Test prompt includes sample page content."""
        sample_pages = ["This is a loan application form", "Interest rates table"]
        prompt = build_classification_prompt(sample_pages)
        assert "loan application form" in prompt
        assert "Interest rates table" in prompt

    def test_prompt_contains_all_categories(self):
        """Test prompt lists all document categories."""
        sample_pages = ["Sample content"]
        prompt = build_classification_prompt(sample_pages)
        for category in DocumentCategory:
            assert category.value in prompt

    def test_system_prompt_exists(self):
        """Test system prompt is defined."""
        assert CLASSIFICATION_SYSTEM_PROMPT
        assert len(CLASSIFICATION_SYSTEM_PROMPT) > 100

    def test_prompt_requests_json_format(self):
        """Test prompt requests JSON format response."""
        sample_pages = ["Content"]
        prompt = build_classification_prompt(sample_pages)
        assert "JSON" in prompt or "json" in prompt
