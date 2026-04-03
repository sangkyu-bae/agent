"""Tests for LLMConfig value object."""
import pytest

from src.domain.compressor.value_objects.llm_config import LLMConfig


class TestLLMConfigCreation:
    """Tests for LLMConfig creation and validation."""

    def test_create_llm_config_with_required_fields(self):
        """LLMConfig should be created with provider and model_name."""
        config = LLMConfig(provider="openai", model_name="gpt-4o-mini")

        assert config.provider == "openai"
        assert config.model_name == "gpt-4o-mini"

    def test_create_llm_config_with_default_values(self):
        """LLMConfig should have default values for optional fields."""
        config = LLMConfig(provider="openai", model_name="gpt-4o-mini")

        assert config.temperature == 0.0
        assert config.max_tokens == 1000
        assert config.api_key is None

    def test_create_llm_config_with_custom_values(self):
        """LLMConfig should accept custom values for all fields."""
        config = LLMConfig(
            provider="anthropic",
            model_name="claude-3-sonnet",
            temperature=0.7,
            max_tokens=2000,
            api_key="test-api-key",
        )

        assert config.provider == "anthropic"
        assert config.model_name == "claude-3-sonnet"
        assert config.temperature == 0.7
        assert config.max_tokens == 2000
        assert config.api_key == "test-api-key"

    def test_llm_config_is_immutable(self):
        """LLMConfig should be immutable (frozen dataclass)."""
        config = LLMConfig(provider="openai", model_name="gpt-4o-mini")

        with pytest.raises(AttributeError):
            config.provider = "anthropic"


class TestLLMConfigValidation:
    """Tests for LLMConfig validation rules."""

    def test_provider_cannot_be_empty(self):
        """Provider should not be empty string."""
        with pytest.raises(ValueError, match="provider"):
            LLMConfig(provider="", model_name="gpt-4o-mini")

    def test_provider_cannot_be_whitespace_only(self):
        """Provider should not be whitespace only."""
        with pytest.raises(ValueError, match="provider"):
            LLMConfig(provider="   ", model_name="gpt-4o-mini")

    def test_model_name_cannot_be_empty(self):
        """Model name should not be empty string."""
        with pytest.raises(ValueError, match="model_name"):
            LLMConfig(provider="openai", model_name="")

    def test_model_name_cannot_be_whitespace_only(self):
        """Model name should not be whitespace only."""
        with pytest.raises(ValueError, match="model_name"):
            LLMConfig(provider="openai", model_name="   ")

    def test_temperature_minimum_is_zero(self):
        """Temperature should not be less than 0.0."""
        with pytest.raises(ValueError, match="temperature"):
            LLMConfig(provider="openai", model_name="gpt-4o-mini", temperature=-0.1)

    def test_temperature_maximum_is_two(self):
        """Temperature should not be greater than 2.0."""
        with pytest.raises(ValueError, match="temperature"):
            LLMConfig(provider="openai", model_name="gpt-4o-mini", temperature=2.1)

    def test_temperature_boundary_zero_is_valid(self):
        """Temperature 0.0 should be valid."""
        config = LLMConfig(provider="openai", model_name="gpt-4o-mini", temperature=0.0)
        assert config.temperature == 0.0

    def test_temperature_boundary_two_is_valid(self):
        """Temperature 2.0 should be valid."""
        config = LLMConfig(provider="openai", model_name="gpt-4o-mini", temperature=2.0)
        assert config.temperature == 2.0

    def test_max_tokens_must_be_positive(self):
        """Max tokens should be greater than 0."""
        with pytest.raises(ValueError, match="max_tokens"):
            LLMConfig(provider="openai", model_name="gpt-4o-mini", max_tokens=0)

    def test_max_tokens_cannot_be_negative(self):
        """Max tokens should not be negative."""
        with pytest.raises(ValueError, match="max_tokens"):
            LLMConfig(provider="openai", model_name="gpt-4o-mini", max_tokens=-1)


class TestLLMConfigEquality:
    """Tests for LLMConfig equality comparison."""

    def test_equal_configs_are_equal(self):
        """Two configs with same values should be equal."""
        config1 = LLMConfig(provider="openai", model_name="gpt-4o-mini")
        config2 = LLMConfig(provider="openai", model_name="gpt-4o-mini")

        assert config1 == config2

    def test_different_providers_are_not_equal(self):
        """Configs with different providers should not be equal."""
        config1 = LLMConfig(provider="openai", model_name="gpt-4o-mini")
        config2 = LLMConfig(provider="anthropic", model_name="gpt-4o-mini")

        assert config1 != config2

    def test_different_models_are_not_equal(self):
        """Configs with different model names should not be equal."""
        config1 = LLMConfig(provider="openai", model_name="gpt-4o-mini")
        config2 = LLMConfig(provider="openai", model_name="gpt-4")

        assert config1 != config2
