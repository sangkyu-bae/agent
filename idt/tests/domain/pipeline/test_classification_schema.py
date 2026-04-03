"""Tests for classification schema."""
import pytest
from pydantic import ValidationError

from src.domain.pipeline.schemas.classification_schema import ClassificationResult
from src.domain.pipeline.enums.document_category import DocumentCategory


class TestClassificationResultValidation:
    """Test ClassificationResult validation."""

    def test_valid_classification_result(self):
        """Test creating valid ClassificationResult."""
        result = ClassificationResult(
            category=DocumentCategory.IT_SYSTEM,
            confidence=0.95,
            reasoning="Technical documentation with system specifications",
        )
        assert result.category == DocumentCategory.IT_SYSTEM
        assert result.confidence == 0.95
        assert result.reasoning == "Technical documentation with system specifications"

    def test_confidence_must_be_between_0_and_1(self):
        """Test confidence must be in [0.0, 1.0]."""
        # Valid boundary values
        result_low = ClassificationResult(
            category=DocumentCategory.GENERAL,
            confidence=0.0,
            reasoning="Low confidence",
        )
        assert result_low.confidence == 0.0

        result_high = ClassificationResult(
            category=DocumentCategory.GENERAL,
            confidence=1.0,
            reasoning="High confidence",
        )
        assert result_high.confidence == 1.0

    def test_confidence_below_zero_raises_error(self):
        """Test confidence below 0 raises ValidationError."""
        with pytest.raises(ValidationError):
            ClassificationResult(
                category=DocumentCategory.GENERAL,
                confidence=-0.1,
                reasoning="Invalid",
            )

    def test_confidence_above_one_raises_error(self):
        """Test confidence above 1 raises ValidationError."""
        with pytest.raises(ValidationError):
            ClassificationResult(
                category=DocumentCategory.GENERAL,
                confidence=1.1,
                reasoning="Invalid",
            )

    def test_all_categories_are_valid(self):
        """Test all DocumentCategory values are accepted."""
        for category in DocumentCategory:
            result = ClassificationResult(
                category=category,
                confidence=0.5,
                reasoning=f"Classified as {category.value}",
            )
            assert result.category == category


class TestClassificationResultSerialization:
    """Test ClassificationResult serialization."""

    def test_model_dump_returns_dict(self):
        """Test model_dump returns dictionary."""
        result = ClassificationResult(
            category=DocumentCategory.HR,
            confidence=0.8,
            reasoning="HR policy document",
        )
        data = result.model_dump()
        assert isinstance(data, dict)
        assert data["category"] == DocumentCategory.HR
        assert data["confidence"] == 0.8
        assert data["reasoning"] == "HR policy document"

    def test_model_dump_json_serializable(self):
        """Test model can be serialized to JSON."""
        result = ClassificationResult(
            category=DocumentCategory.LOAN_FINANCE,
            confidence=0.75,
            reasoning="Loan terms document",
        )
        json_str = result.model_dump_json()
        assert isinstance(json_str, str)
        assert "loan_finance" in json_str
        assert "0.75" in json_str
