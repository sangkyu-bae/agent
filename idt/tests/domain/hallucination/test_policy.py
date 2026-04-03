"""Tests for HallucinationPolicy."""

import pytest

from src.domain.hallucination.policy import HallucinationPolicy


class TestHallucinationPolicy:
    """Tests for HallucinationPolicy.requires_evaluation."""

    def test_requires_evaluation_valid_input_returns_true(self) -> None:
        """Valid input with non-empty generation and documents should return True."""
        result = HallucinationPolicy.requires_evaluation(
            generation="This is a valid answer.",
            documents=["Document content here."]
        )
        assert result is True

    def test_requires_evaluation_empty_generation_returns_false(self) -> None:
        """Empty generation string should return False."""
        result = HallucinationPolicy.requires_evaluation(
            generation="",
            documents=["Document content here."]
        )
        assert result is False

    def test_requires_evaluation_whitespace_generation_returns_false(self) -> None:
        """Whitespace-only generation should return False."""
        result = HallucinationPolicy.requires_evaluation(
            generation="   ",
            documents=["Document content here."]
        )
        assert result is False

    def test_requires_evaluation_empty_documents_returns_false(self) -> None:
        """Empty documents list should return False."""
        result = HallucinationPolicy.requires_evaluation(
            generation="This is a valid answer.",
            documents=[]
        )
        assert result is False

    def test_requires_evaluation_none_generation_returns_false(self) -> None:
        """None generation should return False."""
        result = HallucinationPolicy.requires_evaluation(
            generation=None,
            documents=["Document content here."]
        )
        assert result is False

    def test_requires_evaluation_multiple_documents(self) -> None:
        """Multiple documents should return True."""
        result = HallucinationPolicy.requires_evaluation(
            generation="Answer based on documents.",
            documents=["Doc 1", "Doc 2", "Doc 3"]
        )
        assert result is True

    def test_requires_evaluation_documents_with_empty_strings(self) -> None:
        """Documents list with only empty strings should return False."""
        result = HallucinationPolicy.requires_evaluation(
            generation="Answer here.",
            documents=["", "   ", ""]
        )
        assert result is False

    def test_requires_evaluation_documents_with_some_valid(self) -> None:
        """Documents list with at least one valid document should return True."""
        result = HallucinationPolicy.requires_evaluation(
            generation="Answer here.",
            documents=["", "Valid document", ""]
        )
        assert result is True
