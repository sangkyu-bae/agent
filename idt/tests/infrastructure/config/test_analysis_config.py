"""Tests for AnalysisConfig."""

import pytest

from src.infrastructure.config.analysis_config import AnalysisConfig
from src.domain.policies.analysis_policy import (
    AnalysisRetryPolicy,
    AnalysisQualityThreshold,
)


class TestAnalysisConfig:

    def test_default_values(self):
        config = AnalysisConfig()
        assert config.ANALYSIS_MAX_RETRIES == 3
        assert config.ANALYSIS_RETRY_ON_HALLUCINATION is True
        assert config.ANALYSIS_REQUIRE_WEB_SEARCH_ON_RETRY is True
        assert config.ANALYSIS_MIN_CONFIDENCE_SCORE == 0.7
        assert config.ANALYSIS_MAX_HALLUCINATION_SCORE == 0.3

    def test_get_retry_policy(self):
        config = AnalysisConfig()
        policy = config.get_retry_policy()

        assert isinstance(policy, AnalysisRetryPolicy)
        assert policy.max_retries == 3
        assert policy.retry_on_hallucination is True
        assert policy.require_web_search_on_retry is True

    def test_get_quality_threshold(self):
        config = AnalysisConfig()
        threshold = config.get_quality_threshold()

        assert isinstance(threshold, AnalysisQualityThreshold)
        assert threshold.min_confidence_score == 0.7
        assert threshold.max_hallucination_score == 0.3

    def test_override_values(self, monkeypatch):
        monkeypatch.setenv("ANALYSIS_MAX_RETRIES", "5")
        monkeypatch.setenv("ANALYSIS_MIN_CONFIDENCE_SCORE", "0.9")
        monkeypatch.setenv("ANALYSIS_MAX_HALLUCINATION_SCORE", "0.1")
        monkeypatch.setenv("ANALYSIS_RETRY_ON_HALLUCINATION", "false")

        config = AnalysisConfig()

        assert config.ANALYSIS_MAX_RETRIES == 5
        assert config.ANALYSIS_MIN_CONFIDENCE_SCORE == 0.9
        assert config.ANALYSIS_MAX_HALLUCINATION_SCORE == 0.1
        assert config.ANALYSIS_RETRY_ON_HALLUCINATION is False

    def test_override_affects_policy(self, monkeypatch):
        monkeypatch.setenv("ANALYSIS_MAX_RETRIES", "2")
        config = AnalysisConfig()
        policy = config.get_retry_policy()
        assert policy.max_retries == 2

    def test_override_affects_threshold(self, monkeypatch):
        monkeypatch.setenv("ANALYSIS_MIN_CONFIDENCE_SCORE", "0.85")
        config = AnalysisConfig()
        threshold = config.get_quality_threshold()
        assert threshold.min_confidence_score == 0.85
