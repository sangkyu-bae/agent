"""Custom exceptions for Ollama LLM client."""


class OllamaLLMError(Exception):
    """Base exception for Ollama LLM errors."""

    pass


class OllamaConnectionError(OllamaLLMError):
    """Ollama server connection failure."""

    pass


class OllamaTimeoutError(OllamaLLMError):
    """Request timeout."""

    pass


class OllamaModelNotFoundError(OllamaLLMError):
    """Requested model is not installed locally."""

    pass


class OllamaInvalidRequestError(OllamaLLMError):
    """Invalid request parameters."""

    pass
