"""Tests for RelevanceResult value object."""
import pytest

from src.domain.compressor.value_objects.relevance_result import RelevanceResult


class TestRelevanceResultCreation:
    """Tests for RelevanceResult creation."""

    def test_create_relevance_result_with_required_fields(self):
        """RelevanceResult should be created with is_relevant and score."""
        result = RelevanceResult(is_relevant=True, score=0.85)

        assert result.is_relevant is True
        assert result.score == 0.85

    def test_create_relevance_result_with_reasoning(self):
        """RelevanceResult should accept optional reasoning."""
        result = RelevanceResult(
            is_relevant=True,
            score=0.9,
            reasoning="Document directly answers the query",
        )

        assert result.reasoning == "Document directly answers the query"

    def test_create_relevance_result_without_reasoning(self):
        """RelevanceResult reasoning should default to None."""
        result = RelevanceResult(is_relevant=False, score=0.2)

        assert result.reasoning is None

    def test_relevance_result_is_immutable(self):
        """RelevanceResult should be immutable (frozen dataclass)."""
        result = RelevanceResult(is_relevant=True, score=0.5)

        with pytest.raises(AttributeError):
            result.is_relevant = False


class TestRelevanceResultValidation:
    """Tests for RelevanceResult validation rules."""

    def test_score_minimum_is_zero(self):
        """Score should not be less than 0.0."""
        with pytest.raises(ValueError, match="score"):
            RelevanceResult(is_relevant=True, score=-0.1)

    def test_score_maximum_is_one(self):
        """Score should not be greater than 1.0."""
        with pytest.raises(ValueError, match="score"):
            RelevanceResult(is_relevant=True, score=1.1)

    def test_score_boundary_zero_is_valid(self):
        """Score 0.0 should be valid."""
        result = RelevanceResult(is_relevant=False, score=0.0)
        assert result.score == 0.0

    def test_score_boundary_one_is_valid(self):
        """Score 1.0 should be valid."""
        result = RelevanceResult(is_relevant=True, score=1.0)
        assert result.score == 1.0


class TestRelevanceResultEquality:
    """Tests for RelevanceResult equality."""

    def test_equal_results_are_equal(self):
        """Two results with same values should be equal."""
        result1 = RelevanceResult(is_relevant=True, score=0.8, reasoning="reason")
        result2 = RelevanceResult(is_relevant=True, score=0.8, reasoning="reason")

        assert result1 == result2

    def test_different_is_relevant_are_not_equal(self):
        """Results with different is_relevant should not be equal."""
        result1 = RelevanceResult(is_relevant=True, score=0.8)
        result2 = RelevanceResult(is_relevant=False, score=0.8)

        assert result1 != result2

    def test_different_scores_are_not_equal(self):
        """Results with different scores should not be equal."""
        result1 = RelevanceResult(is_relevant=True, score=0.8)
        result2 = RelevanceResult(is_relevant=True, score=0.9)

        assert result1 != result2
