"""Tests for CompressorConfig value object."""
import pytest

from src.domain.compressor.value_objects.compressor_config import CompressorConfig


class TestCompressorConfigCreation:
    """Tests for CompressorConfig creation."""

    def test_create_compressor_config_with_defaults(self):
        """CompressorConfig should be created with default values."""
        config = CompressorConfig()

        assert config.relevance_threshold == 0.5
        assert config.max_concurrency == 10
        assert config.timeout_seconds == 30.0
        assert config.include_reasoning is True
        assert config.retry_count == 3

    def test_create_compressor_config_with_custom_values(self):
        """CompressorConfig should accept custom values for all fields."""
        config = CompressorConfig(
            relevance_threshold=0.7,
            max_concurrency=5,
            timeout_seconds=60.0,
            include_reasoning=False,
            retry_count=5,
        )

        assert config.relevance_threshold == 0.7
        assert config.max_concurrency == 5
        assert config.timeout_seconds == 60.0
        assert config.include_reasoning is False
        assert config.retry_count == 5

    def test_compressor_config_is_immutable(self):
        """CompressorConfig should be immutable (frozen dataclass)."""
        config = CompressorConfig()

        with pytest.raises(AttributeError):
            config.relevance_threshold = 0.9


class TestCompressorConfigValidation:
    """Tests for CompressorConfig validation rules."""

    def test_relevance_threshold_minimum_is_zero(self):
        """Relevance threshold should not be less than 0.0."""
        with pytest.raises(ValueError, match="relevance_threshold"):
            CompressorConfig(relevance_threshold=-0.1)

    def test_relevance_threshold_maximum_is_one(self):
        """Relevance threshold should not be greater than 1.0."""
        with pytest.raises(ValueError, match="relevance_threshold"):
            CompressorConfig(relevance_threshold=1.1)

    def test_relevance_threshold_boundary_zero_is_valid(self):
        """Relevance threshold 0.0 should be valid."""
        config = CompressorConfig(relevance_threshold=0.0)
        assert config.relevance_threshold == 0.0

    def test_relevance_threshold_boundary_one_is_valid(self):
        """Relevance threshold 1.0 should be valid."""
        config = CompressorConfig(relevance_threshold=1.0)
        assert config.relevance_threshold == 1.0

    def test_max_concurrency_must_be_positive(self):
        """Max concurrency should be greater than 0."""
        with pytest.raises(ValueError, match="max_concurrency"):
            CompressorConfig(max_concurrency=0)

    def test_max_concurrency_cannot_be_negative(self):
        """Max concurrency should not be negative."""
        with pytest.raises(ValueError, match="max_concurrency"):
            CompressorConfig(max_concurrency=-1)

    def test_timeout_seconds_must_be_positive(self):
        """Timeout seconds should be greater than 0."""
        with pytest.raises(ValueError, match="timeout_seconds"):
            CompressorConfig(timeout_seconds=0.0)

    def test_timeout_seconds_cannot_be_negative(self):
        """Timeout seconds should not be negative."""
        with pytest.raises(ValueError, match="timeout_seconds"):
            CompressorConfig(timeout_seconds=-1.0)

    def test_retry_count_minimum_is_zero(self):
        """Retry count can be 0 (no retries)."""
        config = CompressorConfig(retry_count=0)
        assert config.retry_count == 0

    def test_retry_count_cannot_be_negative(self):
        """Retry count should not be negative."""
        with pytest.raises(ValueError, match="retry_count"):
            CompressorConfig(retry_count=-1)


class TestCompressorConfigEquality:
    """Tests for CompressorConfig equality."""

    def test_equal_configs_are_equal(self):
        """Two configs with same values should be equal."""
        config1 = CompressorConfig()
        config2 = CompressorConfig()

        assert config1 == config2

    def test_different_thresholds_are_not_equal(self):
        """Configs with different thresholds should not be equal."""
        config1 = CompressorConfig(relevance_threshold=0.5)
        config2 = CompressorConfig(relevance_threshold=0.7)

        assert config1 != config2

    def test_different_concurrency_are_not_equal(self):
        """Configs with different max_concurrency should not be equal."""
        config1 = CompressorConfig(max_concurrency=10)
        config2 = CompressorConfig(max_concurrency=5)

        assert config1 != config2
