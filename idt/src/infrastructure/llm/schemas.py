"""Request and response schemas for Claude LLM client."""
import uuid
from dataclasses import dataclass, field
from enum import Enum


class ClaudeModel(str, Enum):
    """Supported Claude models."""

    OPUS_4_5 = "claude-opus-4-5-20251101"
    SONNET_4_5 = "claude-sonnet-4-5-20250929"
    HAIKU_4_5 = "claude-haiku-4-5-20251001"


@dataclass
class ClaudeRequest:
    """Claude API request schema."""

    model: ClaudeModel
    messages: list[dict[str, str]]
    system: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.7
    stream: bool = False
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        self._validate_messages()
        self._validate_max_tokens()
        self._validate_temperature()

    def _validate_messages(self) -> None:
        if not self.messages:
            raise ValueError("messages must not be empty")
        for msg in self.messages:
            if "role" not in msg or "content" not in msg:
                raise ValueError("Each message must have 'role' and 'content'")

    def _validate_max_tokens(self) -> None:
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be greater than 0")

    def _validate_temperature(self) -> None:
        if self.temperature < 0.0 or self.temperature > 1.0:
            raise ValueError("temperature must be between 0.0 and 1.0")


@dataclass
class ClaudeResponse:
    """Claude API response schema."""

    content: str
    model: str
    stop_reason: str
    input_tokens: int
    output_tokens: int
    request_id: str
    latency_ms: int
