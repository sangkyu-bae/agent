"""Tests for Claude LLM exception classes."""
import pytest

from src.infrastructure.llm.exceptions import (
    ClaudeAPIError,
    ClaudeInvalidRequestError,
    ClaudeLLMError,
    ClaudeRateLimitError,
    ClaudeTimeoutError,
)


class TestClaudeLLMError:
    def test_is_base_exception(self):
        error = ClaudeLLMError("base error")
        assert isinstance(error, Exception)

    def test_message_preserved(self):
        error = ClaudeLLMError("something went wrong")
        assert str(error) == "something went wrong"


class TestClaudeAPIError:
    def test_inherits_from_base(self):
        error = ClaudeAPIError("api error")
        assert isinstance(error, ClaudeLLMError)

    def test_stores_status_code(self):
        error = ClaudeAPIError("server error", status_code=500)
        assert error.status_code == 500

    def test_status_code_defaults_to_none(self):
        error = ClaudeAPIError("api error")
        assert error.status_code is None

    def test_message_preserved(self):
        error = ClaudeAPIError("server error", status_code=500)
        assert str(error) == "server error"


class TestClaudeRateLimitError:
    def test_inherits_from_base(self):
        error = ClaudeRateLimitError("rate limit")
        assert isinstance(error, ClaudeLLMError)

    def test_message_preserved(self):
        error = ClaudeRateLimitError("429 too many requests")
        assert str(error) == "429 too many requests"


class TestClaudeTimeoutError:
    def test_inherits_from_base(self):
        error = ClaudeTimeoutError("timeout")
        assert isinstance(error, ClaudeLLMError)

    def test_message_preserved(self):
        error = ClaudeTimeoutError("request timed out")
        assert str(error) == "request timed out"


class TestClaudeInvalidRequestError:
    def test_inherits_from_base(self):
        error = ClaudeInvalidRequestError("bad request")
        assert isinstance(error, ClaudeLLMError)

    def test_message_preserved(self):
        error = ClaudeInvalidRequestError("invalid model")
        assert str(error) == "invalid model"
