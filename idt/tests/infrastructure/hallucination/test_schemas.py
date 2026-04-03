"""Tests for hallucination output schema."""

import pytest
from pydantic import BaseModel, ValidationError

from src.infrastructure.hallucination.schemas import HallucinationOutput


class TestHallucinationOutput:
    """Tests for HallucinationOutput schema."""

    def test_is_pydantic_basemodel(self) -> None:
        """HallucinationOutput should be a Pydantic BaseModel."""
        assert issubclass(HallucinationOutput, BaseModel)

    def test_is_hallucinated_field_true(self) -> None:
        """is_hallucinated field should accept True."""
        output = HallucinationOutput(is_hallucinated=True)
        assert output.is_hallucinated is True

    def test_is_hallucinated_field_false(self) -> None:
        """is_hallucinated field should accept False."""
        output = HallucinationOutput(is_hallucinated=False)
        assert output.is_hallucinated is False

    def test_is_hallucinated_field_required(self) -> None:
        """is_hallucinated field should be required."""
        with pytest.raises(ValidationError):
            HallucinationOutput()

    def test_is_hallucinated_field_must_be_bool(self) -> None:
        """is_hallucinated field must be boolean."""
        with pytest.raises(ValidationError):
            HallucinationOutput(is_hallucinated="invalid")
