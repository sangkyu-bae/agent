"""Request and response schemas for Ollama LLM client."""
import uuid
from dataclasses import dataclass, field
from enum import Enum


class OllamaModel(str, Enum):
    """Supported Ollama models (must be installed locally via `ollama pull`)."""

    LLAMA3_2 = "llama3.2"
    LLAMA3_1 = "llama3.1"
    MISTRAL = "mistral"
    GEMMA2 = "gemma2"
    QWEN2_5 = "qwen2.5"
    DEEPSEEK_R1 = "deepseek-r1"


@dataclass
class OllamaRequest:
    """Ollama API request schema.

    model accepts either an OllamaModel enum value or an arbitrary model name
    string (e.g. "phi3:mini", "llama3.2:1b") so callers can use any locally
    installed model without having to extend the enum.
    """

    model: "OllamaModel | str"
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
class OllamaResponse:
    """Ollama API response schema."""

    content: str
    model: str
    stop_reason: str          # "stop" | "length" | "unknown"
    input_tokens: int
    output_tokens: int
    request_id: str
    latency_ms: int
