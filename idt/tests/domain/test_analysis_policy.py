"""Tests for AnalysisRetryPolicy and AnalysisQualityThreshold."""

import pytest

from src.domain.policies.analysis_policy import (
    AnalysisRetryPolicy,
    AnalysisQualityThreshold,
)


class TestAnalysisRetryPolicy:

    def test_should_retry_within_limit(self):
        policy = AnalysisRetryPolicy(max_retries=3)
        assert policy.should_retry(attempt=1, has_hallucination=True) is True
        assert policy.should_retry(attempt=2, has_hallucination=True) is True

    def test_should_not_retry_exceeded_limit(self):
        policy = AnalysisRetryPolicy(max_retries=3)
        assert policy.should_retry(attempt=3, has_hallucination=True) is False

    def test_should_not_retry_no_hallucination(self):
        policy = AnalysisRetryPolicy(max_retries=3, retry_on_hallucination=True)
        assert policy.should_retry(attempt=1, has_hallucination=False) is False

    def test_validate_max_retries_too_low(self):
        with pytest.raises(ValueError):
            AnalysisRetryPolicy(max_retries=0).validate()

    def test_validate_max_retries_too_high(self):
        with pytest.raises(ValueError):
            AnalysisRetryPolicy(max_retries=10).validate()

    def test_validate_valid_policy(self):
        policy = AnalysisRetryPolicy(max_retries=3)
        policy.validate()  # should not raise

    def test_retry_on_hallucination_disabled(self):
        policy = AnalysisRetryPolicy(max_retries=3, retry_on_hallucination=False)
        assert policy.should_retry(attempt=1, has_hallucination=True) is False


class TestAnalysisQualityThreshold:

    def test_is_acceptable_good_quality(self):
        threshold = AnalysisQualityThreshold(
            min_confidence_score=0.7,
            max_hallucination_score=0.3,
        )
        assert threshold.is_acceptable(confidence=0.8, hallucination=0.2) is True

    def test_is_acceptable_low_confidence(self):
        threshold = AnalysisQualityThreshold(min_confidence_score=0.7)
        assert threshold.is_acceptable(confidence=0.6, hallucination=0.2) is False

    def test_is_acceptable_high_hallucination(self):
        threshold = AnalysisQualityThreshold(max_hallucination_score=0.3)
        assert threshold.is_acceptable(confidence=0.8, hallucination=0.4) is False

    def test_validate_invalid_confidence(self):
        with pytest.raises(ValueError):
            AnalysisQualityThreshold(min_confidence_score=1.5).validate()

    def test_validate_invalid_hallucination(self):
        with pytest.raises(ValueError):
            AnalysisQualityThreshold(max_hallucination_score=-0.1).validate()

    def test_validate_valid_threshold(self):
        threshold = AnalysisQualityThreshold(
            min_confidence_score=0.7,
            max_hallucination_score=0.3,
        )
        threshold.validate()  # should not raise

    def test_boundary_values_acceptable(self):
        threshold = AnalysisQualityThreshold(
            min_confidence_score=0.7,
            max_hallucination_score=0.3,
        )
        assert threshold.is_acceptable(confidence=0.7, hallucination=0.3) is True

    def test_boundary_values_not_acceptable(self):
        threshold = AnalysisQualityThreshold(
            min_confidence_score=0.7,
            max_hallucination_score=0.3,
        )
        assert threshold.is_acceptable(confidence=0.69, hallucination=0.31) is False
