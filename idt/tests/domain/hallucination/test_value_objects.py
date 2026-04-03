"""Tests for HallucinationEvaluationResult value object."""

import pytest
from pydantic import BaseModel, ValidationError

from src.domain.hallucination.value_objects import HallucinationEvaluationResult


class TestHallucinationEvaluationResult:
    """Tests for HallucinationEvaluationResult."""

    def test_is_pydantic_basemodel(self) -> None:
        """HallucinationEvaluationResult should be a Pydantic BaseModel."""
        assert issubclass(HallucinationEvaluationResult, BaseModel)

    def test_is_hallucinated_field_true(self) -> None:
        """is_hallucinated field should accept True."""
        result = HallucinationEvaluationResult(is_hallucinated=True)
        assert result.is_hallucinated is True

    def test_is_hallucinated_field_false(self) -> None:
        """is_hallucinated field should accept False."""
        result = HallucinationEvaluationResult(is_hallucinated=False)
        assert result.is_hallucinated is False

    def test_is_hallucinated_field_required(self) -> None:
        """is_hallucinated field should be required."""
        with pytest.raises(ValidationError):
            HallucinationEvaluationResult()

    def test_is_hallucinated_field_must_be_bool(self) -> None:
        """is_hallucinated field must be boolean."""
        with pytest.raises(ValidationError):
            HallucinationEvaluationResult(is_hallucinated="not a bool")
