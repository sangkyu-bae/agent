"""LLMConfig value object for LLM provider configuration."""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LLMConfig:
    """Configuration for LLM providers.

    Attributes:
        provider: The LLM provider name (e.g., "openai", "anthropic").
        model_name: The model identifier (e.g., "gpt-4o-mini").
        temperature: Sampling temperature, between 0.0 and 2.0.
        max_tokens: Maximum tokens in the response.
        api_key: Optional API key for the provider.
    """

    provider: str
    model_name: str
    temperature: float = 0.0
    max_tokens: int = 1000
    api_key: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate the configuration after initialization."""
        self._validate_provider()
        self._validate_model_name()
        self._validate_temperature()
        self._validate_max_tokens()

    def _validate_provider(self) -> None:
        if not self.provider or not self.provider.strip():
            raise ValueError("provider must not be empty")

    def _validate_model_name(self) -> None:
        if not self.model_name or not self.model_name.strip():
            raise ValueError("model_name must not be empty")

    def _validate_temperature(self) -> None:
        if self.temperature < 0.0 or self.temperature > 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0")

    def _validate_max_tokens(self) -> None:
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be greater than 0")
