"""Custom exceptions for Claude LLM client."""


class ClaudeLLMError(Exception):
    """Base exception for Claude LLM errors."""

    pass


class ClaudeAPIError(ClaudeLLMError):
    """API call failure (5xx errors)."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class ClaudeRateLimitError(ClaudeLLMError):
    """Rate limit exceeded (429)."""

    pass


class ClaudeTimeoutError(ClaudeLLMError):
    """Request timeout."""

    pass


class ClaudeInvalidRequestError(ClaudeLLMError):
    """Invalid request (4xx client errors)."""

    pass
